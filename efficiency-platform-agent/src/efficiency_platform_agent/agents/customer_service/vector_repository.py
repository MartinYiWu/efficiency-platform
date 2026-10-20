"""智能客服文档分块与索引成员的 pgvector 仓储。"""

from __future__ import annotations

import inspect
from collections import defaultdict
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid5

from pgvector import Vector

from .contracts import ChunkDraft, IndexDocumentMember, IndexVerificationResult

_CHUNK_NAMESPACE = UUID("38e6afe9-28d1-46ef-b538-d59c74b4f6e9")


class IndexVerificationError(RuntimeError):
    code = "KB_INDEX_VERIFY_FAILED"

    def __init__(self, message: str = "KB_INDEX_VERIFY_FAILED") -> None:
        super().__init__(message)


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _rows(result: Any) -> tuple[Any, ...]:
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return tuple(await _await(fetchall()))
    return tuple(result or ())


class DocumentChunkRepository:
    """只访问 Agent 自有 customer_service Schema。"""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def replace_version_chunks(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        document_id: str,
        document_version_id: str,
        chunks: tuple[ChunkDraft, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None:
        if not chunks or len(chunks) != len(embeddings):
            raise ValueError("EMBEDDING_COUNT_MISMATCH")
        if any(len(item) != 1024 for item in embeddings):
            raise ValueError("EMBEDDING_DIMENSION_INVALID")
        if tuple(item.chunk_no for item in chunks) != tuple(range(1, len(chunks) + 1)):
            raise ValueError("CHUNK_SEQUENCE_INVALID")
        parameters = tuple(
            (
                str(
                    uuid5(
                        _CHUNK_NAMESPACE,
                        f"{document_version_id}:{chunk.chunk_no}:{chunk.content_hash}",
                    )
                ),
                tenant_id,
                knowledge_base_id,
                document_id,
                document_version_id,
                chunk.chunk_no,
                chunk.section_path,
                chunk.page_no,
                chunk.content,
                chunk.content_hash,
                chunk.token_count,
                Vector(list(embedding)),
                "text-embedding-v4",
                1024,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )
        async with self.connection.transaction():
            await _await(
                self.connection.execute(
                    "DELETE FROM customer_service.document_chunk "
                    "WHERE document_version_id = %s",
                    (document_version_id,),
                )
            )
            await _await(
                self.connection.executemany(
                    "INSERT INTO customer_service.document_chunk "
                    "(chunk_id, tenant_id, knowledge_base_id, document_id, "
                    "document_version_id, chunk_no, section_path, page_no, content, "
                    "content_hash, token_count, embedding, embedding_model, "
                    "embedding_dimension) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    parameters,
                )
            )

    async def sync_and_verify_index_release(
        self,
        release_id: str,
        knowledge_base_id: str,
        documents: tuple[IndexDocumentMember, ...],
    ) -> IndexVerificationResult:
        if len({item.document_id for item in documents}) != len(documents):
            raise IndexVerificationError()
        async with self.connection.transaction():
            await _await(
                self.connection.execute(
                    "DELETE FROM customer_service.index_release_document "
                    "WHERE index_release_id = %s",
                    (release_id,),
                )
            )
            await _await(
                self.connection.executemany(
                    "INSERT INTO customer_service.index_release_document "
                    "(index_release_id, knowledge_base_id, document_id, "
                    "document_version_id, document_sha256) VALUES (%s, %s, %s, %s, %s)",
                    tuple(
                        (
                            release_id,
                            knowledge_base_id,
                            str(item.document_id),
                            str(item.document_version_id),
                            item.document_sha256,
                        )
                        for item in documents
                    ),
                )
            )
            return await self._verify_index_release(release_id)

    async def verify_index_release(self, release_id: str) -> IndexVerificationResult:
        return await self._verify_index_release(release_id)

    async def _verify_index_release(self, release_id: str) -> IndexVerificationResult:
        member_rows = await _rows(
            await _await(
                self.connection.execute(
                    "SELECT document_id::text, document_version_id::text, document_sha256 "
                    "FROM customer_service.index_release_document "
                    "WHERE index_release_id = %s ORDER BY document_id",
                    (release_id,),
                )
            )
        )
        if not member_rows:
            raise IndexVerificationError()
        member_versions = {str(row[1]) for row in member_rows}
        chunk_rows = await _rows(
            await _await(
                self.connection.execute(
                    "SELECT document_version_id::text, chunk_no, content, content_hash, "
                    "embedding_model, embedding_dimension, vector_dims(embedding) "
                    "FROM customer_service.document_chunk "
                    "WHERE document_version_id = ANY(%s::uuid[]) "
                    "ORDER BY document_version_id, chunk_no",
                    (list(member_versions),),
                )
            )
        )
        by_version: dict[str, list[Any]] = defaultdict(list)
        for row in chunk_rows:
            by_version[str(row[0])].append(row)
        if set(by_version) != member_versions:
            raise IndexVerificationError()
        for rows in by_version.values():
            expected = 1
            for row in rows:
                (
                    _,
                    chunk_no,
                    content,
                    content_hash,
                    model,
                    dimension,
                    vector_dimension,
                ) = row
                if (
                    chunk_no != expected
                    or not str(content).strip()
                    or sha256(str(content).encode("utf-8")).hexdigest() != content_hash
                    or model != "text-embedding-v4"
                    or dimension != 1024
                    or vector_dimension != 1024
                ):
                    raise IndexVerificationError()
                expected += 1
        checksum_source = "\n".join(
            f"{row[0]}:{row[1]}:{row[2]}:{len(by_version[str(row[1])])}"
            for row in member_rows
        )
        return IndexVerificationResult(
            release_id=UUID(release_id),
            document_count=len(member_rows),
            chunk_count=len(chunk_rows),
            checksum=sha256(checksum_source.encode("utf-8")).hexdigest(),
        )


__all__ = [
    "DocumentChunkRepository",
    "IndexVerificationError",
]
