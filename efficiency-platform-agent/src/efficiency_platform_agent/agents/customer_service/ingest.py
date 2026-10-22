"""智能客服文档摄取编排。"""

from __future__ import annotations

import asyncio
import inspect
import io
import logging
import traceback
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from efficiency_platform_agent.capabilities.document.preflight import preflight_document

from .chunking import parent_child_document
from .contracts import IngestJobRequest, IngestJobView, IngestStage, ParsedDocument
from .ingest_repository import InMemoryIngestJobRepository
from .parsing import join_pages

logger = logging.getLogger("CustomerServiceIngest")


class HttpDocumentDownloader:
    """只下载 Java 生成的 HTTPS 读取地址，并执行响应大小上限。"""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def download(self, url: str, max_bytes: int) -> bytes:
        async with self.client.stream("GET", url, follow_redirects=False) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is not None and int(content_length) > max_bytes:
                raise ValueError("FILE_SIZE_EXCEEDED")
            body = bytearray()
            async for part in response.aiter_bytes():
                body.extend(part)
                if len(body) > max_bytes:
                    raise ValueError("FILE_SIZE_EXCEEDED")
        return bytes(body)


class CustomerServiceIngestService:
    """将一次摄取固定编排为预检、解析、OCR、分块、向量化和校验。"""

    def __init__(
        self,
        *,
        jobs: InMemoryIngestJobRepository,
        downloader: Any,
        parser: Any,
        ocr: Any,
        embedder: Any,
        vectors: Any,
    ) -> None:
        self.jobs = jobs
        self.downloader = downloader
        self.parser = parser
        self.ocr = ocr
        self.embedder = embedder
        self.vectors = vectors
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, request: IngestJobRequest) -> IngestJobView:
        queued = IngestJobView(
            task_id=request.task_id,
            status="QUEUED",
            stage="PREFLIGHT",
            progress_percent=0,
        )
        current, created = await self.jobs.create(queued)
        if created:
            task = asyncio.create_task(self._process(request))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return current

    async def get(self, task_id: UUID) -> IngestJobView | None:
        return await self.jobs.get(task_id)

    async def verify_index(self, request: Any):
        return await self.vectors.sync_and_verify_index_release(
            str(request.release_id),
            str(request.knowledge_base_id),
            request.documents,
        )

    async def _process(self, request: IngestJobRequest) -> None:
        try:
            await self._progress(request.task_id, "PREFLIGHT", 5)
            content = await self.downloader.download(
                str(request.download_url), request.size_bytes
            )
            if (
                len(content) != request.size_bytes
                or sha256(content).hexdigest() != request.sha256
            ):
                raise _IngestFailure("KB_FILE_DIGEST_MISMATCH", "文件完整性校验失败")
            preflight = preflight_document(
                content, request.file_name, request.content_type
            )
            if preflight.quality_status.value == "rejected":
                raise _IngestFailure("KB_FILE_PREFLIGHT_FAILED", "文件预检失败")

            await self._progress(request.task_id, "PARSE", 20)
            parsed = await _maybe_await(self.parser.parse(content, request.file_name))
            markdown = _markdown(
                parsed, allow_empty=request.content_type == "application/pdf"
            )
            if request.content_type == "application/pdf" and len(markdown.strip()) < 80:
                if self.ocr is None:
                    raise _IngestFailure("KB_OCR_REQUIRED", "扫描文档需要 OCR")
                await self._progress(request.task_id, "OCR", 35)
                parsed = await _ocr_pdf(content, self.ocr)
                markdown = _markdown(parsed)
            page_markers = (
                tuple(parsed.get("page_markers", ()))
                if isinstance(parsed, dict)
                else ()
            )
            document = ParsedDocument(markdown=markdown, page_markers=page_markers)

            await self._progress(request.task_id, "CHUNK", 55)
            parents = parent_child_document(document)
            chunks = tuple(child for parent in parents for child in parent.children)
            await self._progress(request.task_id, "EMBED", 75)
            embeddings = await self.embedder.embed(
                tuple(item.content for item in chunks)
            )
            await self.vectors.replace_version_chunks(
                tenant_id=request.tenant_id,
                knowledge_base_id=str(request.knowledge_base_id),
                document_id=str(request.document_id),
                document_version_id=str(request.document_version_id),
                document_title=request.document_title,
                version_no=request.version_no,
                chunks=chunks,
                embeddings=embeddings,
                parents=parents,
            )
            await self._progress(request.task_id, "VERIFY", 95)
            if len(chunks) != len(embeddings) or any(
                len(vector) != 1024 for vector in embeddings
            ):
                raise _IngestFailure("KB_CHUNK_VERIFY_FAILED", "文档分块校验失败")
            await self.jobs.save(
                IngestJobView(
                    task_id=request.task_id,
                    status="SUCCEEDED",
                    stage="VERIFY",
                    progress_percent=100,
                )
            )
        except asyncio.CancelledError:
            await self.jobs.save(
                IngestJobView(
                    task_id=request.task_id,
                    status="CANCELLED",
                    stage="VERIFY",
                    progress_percent=0,
                    error_code="KB_INGEST_CANCELLED",
                    error_message="文档处理已取消",
                )
            )
            raise
        except Exception as error:  # noqa: BLE001 - 后台任务必须归一化全部失败
            failure = _map_failure(error)
            current = await self.jobs.get(request.task_id)
            frames = " > ".join(
                f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)
            )
            logger.error(
                "event=customer_service_ingest_failed task_id=%s stage=%s "
                "error_code=%s error_type=%s frames=%s",
                request.task_id,
                current.stage if current is not None else "PREFLIGHT",
                failure.code,
                type(error).__name__,
                frames,
            )
            await self.jobs.save(
                IngestJobView(
                    task_id=request.task_id,
                    status="FAILED",
                    stage=current.stage if current is not None else "PREFLIGHT",
                    progress_percent=current.progress_percent
                    if current is not None
                    else 0,
                    error_code=failure.code,
                    error_message=failure.safe_message,
                )
            )

    async def _progress(self, task_id: UUID, stage: IngestStage, percent: int) -> None:
        await self.jobs.save(
            IngestJobView(
                task_id=task_id,
                status="RUNNING",
                stage=stage,
                progress_percent=percent,
            )
        )


class _IngestFailure(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


def _map_failure(error: Exception) -> _IngestFailure:
    if isinstance(error, _IngestFailure):
        return error
    code = getattr(error, "code", None)
    if code == "EMBEDDING_PROVIDER_FAILED":
        return _IngestFailure("KB_EMBEDDING_FAILED", "文档向量生成失败")
    if isinstance(error, ValueError) and str(error) == "PARENT_CLAUSE_TOO_LONG":
        return _IngestFailure(
            "KB_PARENT_CLAUSE_TOO_LONG",
            "完整条款超过安全切分上限，请拆分源文档后更新版本",
        )
    if isinstance(error, ValueError) and str(error) == "FILE_SIZE_EXCEEDED":
        return _IngestFailure("KB_FILE_SIZE_INVALID", "文件大小校验失败")
    return _IngestFailure("KB_INGEST_FAILED", "文档处理失败")


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _markdown(parsed: Any, *, allow_empty: bool = False) -> str:
    if isinstance(parsed, str):
        value = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("text"), str):
        value = parsed["text"]
    else:
        raise _IngestFailure("KB_PARSE_RESULT_INVALID", "文档解析结果无效")
    if not value.strip() and not allow_empty:
        raise _IngestFailure("KB_PARSE_RESULT_EMPTY", "文档解析结果为空")
    return value


async def _ocr_pdf(content: bytes, ocr: Any) -> dict[str, Any]:
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]

        document = pdfium.PdfDocument(content)
        pages: list[str] = []
        for page in document:
            image = page.render(scale=2).to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            result = await _maybe_await(ocr.recognize(buffer.getvalue()))
            pages.append(_ocr_text(result))
        parsed = join_pages(tuple(pages))
    except _IngestFailure:
        raise
    except Exception as error:
        raise _IngestFailure("KB_OCR_FAILED", "文档 OCR 失败") from error
    if not parsed["text"].strip():
        raise _IngestFailure("KB_OCR_EMPTY", "文档 OCR 未识别到文本")
    return parsed


def _ocr_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("rec_texts", "texts", "text"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
            if isinstance(candidate, (list, tuple)):
                return "\n".join(str(item) for item in candidate)
        return "\n".join(_ocr_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_ocr_text(item) for item in value)
    return ""


__all__ = ["CustomerServiceIngestService", "HttpDocumentDownloader"]
