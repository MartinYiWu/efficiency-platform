"""文档摄取薄服务：预检、解析、质量和引用隔离。"""

from __future__ import annotations

import tempfile
from typing import Any

from .contracts import DocumentIngestionResult, DocumentQualityStatus
from .preflight import preflight_document


class DocumentIngestionService:
    """只处理内存输入，临时目录始终在 finally 中清理。"""

    def __init__(self, parser: Any, ocr: Any = None, indexer: Any = None) -> None:
        self.parser, self.ocr, self.indexer = parser, ocr, indexer
        self._processed: set[str] = set()

    async def ingest(
        self, content: bytes, filename: str, mime_type: str, upload_id: str
    ) -> DocumentIngestionResult:
        if upload_id in self._processed:
            return DocumentIngestionResult(
                None,
                DocumentQualityStatus.REVIEW_REQUIRED,
                ("DUPLICATE_UPLOAD",),
                (),
                None,
            )
        preflight = preflight_document(content, filename, mime_type)
        if preflight.quality_status is DocumentQualityStatus.REJECTED:
            return DocumentIngestionResult(
                None, preflight.quality_status, preflight.reason_codes, (), None
            )
        temporary = tempfile.TemporaryDirectory(prefix="agent-doc-")
        try:
            ast = self.parser.parse(content, filename)
            if self.ocr is not None and filename.lower().endswith(
                (".png", ".jpg", ".jpeg")
            ):
                ast = self.ocr.recognize(content)
            if self.indexer is not None:
                self.indexer(ast)
            # 仅在解析和索引均成功后登记，失败请求可以使用相同 upload_id 重试。
            self._processed.add(upload_id)
            return DocumentIngestionResult(
                ast,
                preflight.quality_status,
                preflight.reason_codes,
                (f"chunk-{upload_id}",),
                f"artifact-{upload_id}",
            )
        finally:
            temporary.cleanup()


__all__ = ["DocumentIngestionService"]
