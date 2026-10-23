"""智能客服文档分块与索引成员的 pgvector 仓储。"""

from __future__ import annotations

import inspect
from collections import defaultdict
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid5

from pgvector import Vector

from .contracts import (
    ChunkDraft,
    IndexDocumentMember,
    IndexVerificationResult,
    ParentDraft,
)
from .state import Evidence, ParentEvidence

_CHUNK_NAMESPACE = UUID("38e6afe9-28d1-46ef-b538-d59c74b4f6e9")
_PARENT_NAMESPACE = UUID("a1a161a2-993a-42b7-bb5d-803ec46c4273")


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
        document_title: str,
        version_no: int,
        chunks: tuple[ChunkDraft, ...],
        embeddings: tuple[tuple[float, ...], ...],
        parents: tuple[ParentDraft, ...] = (),
    ) -> None:
        if not chunks or len(chunks) != len(embeddings):
            raise ValueError("EMBEDDING_COUNT_MISMATCH")
        if any(len(item) != 1024 for item in embeddings):
            raise ValueError("EMBEDDING_DIMENSION_INVALID")
        if tuple(item.chunk_no for item in chunks) != tuple(range(1, len(chunks) + 1)):
            raise ValueError("CHUNK_SEQUENCE_INVALID")
        parent_ids = {
            parent.parent_no: str(
                uuid5(
                    _PARENT_NAMESPACE,
                    f"{document_version_id}:{parent.parent_no}:{parent.content_hash}",
                )
            )
            for parent in parents
        }
        if parents and (
            tuple(parent_ids) != tuple(range(1, len(parents) + 1))
            or tuple(child for parent in parents for child in parent.children) != chunks
        ):
            raise ValueError("PARENT_CHILD_RELATION_INVALID")
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
                document_title,
                version_no,
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
            published = await _rows(
                await _await(
                    self.connection.execute(
                        "SELECT 1 FROM customer_service.index_release_document "
                        "WHERE document_version_id = %s LIMIT 1",
                        (document_version_id,),
                    )
                )
            )
            if published:
                raise ValueError("PUBLISHED_DOCUMENT_VERSION_IMMUTABLE")
            await _await(
                self.connection.execute(
                    "DELETE FROM customer_service.document_chunk "
                    "WHERE document_version_id = %s",
                    (document_version_id,),
                )
            )
            if parents:
                await _await(
                    self.connection.execute(
                        "DELETE FROM customer_service.document_parent "
                        "WHERE document_version_id = %s",
                        (document_version_id,),
                    )
                )
                await _await(
                    self.connection.executemany(
                        "INSERT INTO customer_service.document_parent "
                        "(parent_id, tenant_id, knowledge_base_id, document_id, "
                        "document_version_id, document_title, version_no, parent_no, "
                        "section_path, page_start, page_end, content, content_hash, "
                        "token_count, block_kind, evidence_mode, source_table_id) VALUES "
                        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        tuple(
                            (
                                parent_ids[parent.parent_no],
                                tenant_id,
                                knowledge_base_id,
                                document_id,
                                document_version_id,
                                document_title,
                                version_no,
                                parent.parent_no,
                                parent.section_path,
                                parent.page_start,
                                parent.page_end,
                                parent.content,
                                parent.content_hash,
                                parent.token_count,
                                parent.block_kind,
                                parent.evidence_mode,
                                parent.source_table_id,
                            )
                            for parent in parents
                        ),
                    )
                )
                parameters = tuple(
                    row
                    + (
                        parent_ids[chunk.parent_no],
                        chunk.child_no,
                        chunk.start_offset,
                        chunk.end_offset,
                    )
                    for row, chunk in zip(parameters, chunks, strict=True)
                )
            await _await(
                self.connection.executemany(
                    "INSERT INTO customer_service.document_chunk "
                    "(chunk_id, tenant_id, knowledge_base_id, document_id, "
                    "document_version_id, document_title, version_no, chunk_no, "
                    "section_path, page_no, content, "
                    "content_hash, token_count, embedding, embedding_model, "
                    "embedding_dimension"
                    + (
                        ", parent_id, child_no, start_offset, end_offset"
                        if parents
                        else ""
                    )
                    + ") VALUES ("
                    + ", ".join("%s" for _ in range(20 if parents else 16))
                    + ")",
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

    async def get_parents(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        parent_ids: tuple[UUID, ...],
    ) -> tuple[ParentEvidence, ...]:
        if not parent_ids:
            return ()
        result = await _await(
            self.connection.execute(
                "SELECT p.parent_id::text,p.knowledge_base_id::text,p.document_id::text,"
                "p.document_version_id::text,m.index_release_id::text,p.document_title,"
                "p.version_no,p.section_path,p.page_start,p.page_end,p.content,p.content_hash,"
                "p.token_count,p.block_kind,p.evidence_mode,p.parent_no,p.source_table_id "
                "FROM customer_service.document_parent p "
                "JOIN customer_service.index_release_document m "
                "ON m.document_version_id=p.document_version_id "
                "WHERE p.tenant_id=%s AND m.index_release_id=ANY(%s::uuid[]) "
                "AND p.parent_id=ANY(%s::uuid[])",
                (
                    tenant_id,
                    [str(item) for item in index_release_ids],
                    [str(item) for item in parent_ids],
                ),
            )
        )
        return tuple(
            ParentEvidence(
                parent_id=UUID(str(row[0])),
                knowledge_base_id=UUID(str(row[1])),
                document_id=UUID(str(row[2])),
                document_version_id=UUID(str(row[3])),
                index_release_id=UUID(str(row[4])),
                document_title=str(row[5]),
                version_no=int(row[6]),
                section_path=None if row[7] is None else str(row[7]),
                page_no=None if row[8] is None else int(row[8]),
                page_end=None if row[9] is None else int(row[9]),
                content=str(row[10]),
                content_hash=str(row[11]),
                token_count=int(row[12]),
                block_kind=row[13] or "LIST",
                evidence_mode=row[14] or "FULL_ONLY",
                parent_no=int(row[15]),
                source_table_id=None if row[16] is None else int(row[16]),
            )
            for row in await _rows(result)
        )

    async def get_index_members(
        self, *, index_release_ids: tuple[UUID, ...]
    ) -> tuple[tuple[UUID, UUID, UUID, UUID], ...]:
        result = await _await(
            self.connection.execute(
                "SELECT knowledge_base_id::text,document_id::text,document_version_id::text,"
                "index_release_id::text FROM customer_service.index_release_document "
                "WHERE index_release_id=ANY(%s::uuid[])",
                ([str(item) for item in index_release_ids],),
            )
        )
        return tuple(
            tuple(UUID(str(value)) for value in row) for row in await _rows(result)
        )

    async def get_chunk_vectors(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        chunk_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[float, ...]]:
        if not chunk_ids:
            return {}
        result = await _await(
            self.connection.execute(
                "SELECT c.chunk_id::text,c.embedding FROM customer_service.document_chunk c "
                "JOIN customer_service.index_release_document m "
                "ON m.document_version_id=c.document_version_id "
                "AND m.document_id=c.document_id AND m.knowledge_base_id=c.knowledge_base_id "
                "WHERE c.tenant_id=%s AND m.index_release_id=ANY(%s::uuid[]) "
                "AND c.chunk_id=ANY(%s::uuid[])",
                (
                    tenant_id,
                    [str(item) for item in index_release_ids],
                    [str(item) for item in chunk_ids],
                ),
            )
        )
        return {
            UUID(str(row[0])): tuple(float(value) for value in Vector._from_db(row[1]))
            for row in await _rows(result)
        }

    async def vector_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Evidence, ...]:
        if not index_release_ids or len(vector) != 1024 or limit < 1:
            raise ValueError("VECTOR_SEARCH_INPUT_INVALID")
        result = await _await(
            self.connection.execute(
                "SELECT c.chunk_id::text,c.knowledge_base_id::text,c.document_id::text,"
                "c.document_version_id::text,m.index_release_id::text,c.document_title,"
                "c.version_no,c.section_path,c.page_no,c.content,c.content_hash,"
                "c.parent_id::text,c.start_offset,c.end_offset,"
                "1-(c.embedding <=> %s) AS score "
                "FROM customer_service.document_chunk c "
                "JOIN customer_service.index_release_document m "
                "ON m.document_version_id=c.document_version_id "
                "WHERE c.tenant_id=%s AND m.index_release_id=ANY(%s::uuid[]) "
                "ORDER BY c.embedding <=> %s LIMIT %s",
                (
                    Vector(list(vector)),
                    tenant_id,
                    [str(item) for item in index_release_ids],
                    Vector(list(vector)),
                    limit,
                ),
            )
        )
        return self._evidence(await _rows(result))

    async def fts_search(
        self,
        *,
        tenant_id: str,
        index_release_ids: tuple[UUID, ...],
        query: str,
        limit: int,
    ) -> tuple[Evidence, ...]:
        if not index_release_ids or not query.strip() or limit < 1:
            raise ValueError("FTS_SEARCH_INPUT_INVALID")
        result = await _await(
            self.connection.execute(
                "SELECT c.chunk_id::text,c.knowledge_base_id::text,c.document_id::text,"
                "c.document_version_id::text,m.index_release_id::text,c.document_title,"
                "c.version_no,c.section_path,c.page_no,c.content,c.content_hash,"
                "c.parent_id::text,c.start_offset,c.end_offset,"
                "ts_rank_cd(to_tsvector('simple',c.content), plainto_tsquery('simple',%s)) AS score "
                "FROM customer_service.document_chunk c "
                "JOIN customer_service.index_release_document m "
                "ON m.document_version_id=c.document_version_id "
                "WHERE c.tenant_id=%s AND m.index_release_id=ANY(%s::uuid[]) "
                "AND to_tsvector('simple',c.content) @@ plainto_tsquery('simple',%s) "
                "ORDER BY score DESC,c.chunk_id LIMIT %s",
                (
                    query,
                    tenant_id,
                    [str(item) for item in index_release_ids],
                    query,
                    limit,
                ),
            )
        )
        return self._evidence(await _rows(result))

    @staticmethod
    def _evidence(rows: tuple[Any, ...]) -> tuple[Evidence, ...]:
        return tuple(
            Evidence(
                chunk_id=UUID(str(row[0])),
                parent_id=None if row[11] is None else UUID(str(row[11])),
                knowledge_base_id=UUID(str(row[1])),
                document_id=UUID(str(row[2])),
                document_version_id=UUID(str(row[3])),
                index_release_id=UUID(str(row[4])),
                document_title=str(row[5]),
                version_no=int(row[6]),
                section_path=None if row[7] is None else str(row[7]),
                page_no=None if row[8] is None else int(row[8]),
                content=str(row[9]),
                content_hash=str(row[10]),
                hit_start_offset=None if row[12] is None else int(row[12]),
                hit_end_offset=None if row[13] is None else int(row[13]),
                score=float(row[14]),
            )
            for row in rows
        )

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
                    "embedding_model, embedding_dimension, vector_dims(embedding), "
                    "parent_id::text, child_no, start_offset, end_offset "
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
                    parent_id,
                    child_no,
                    start_offset,
                    end_offset,
                ) = row
                if (
                    chunk_no != expected
                    or not str(content).strip()
                    or sha256(str(content).encode("utf-8")).hexdigest() != content_hash
                    or model != "text-embedding-v4"
                    or dimension != 1024
                    or vector_dimension != 1024
                    or (
                        parent_id is not None
                        and (
                            child_no is None
                            or start_offset is None
                            or end_offset is None
                        )
                    )
                ):
                    raise IndexVerificationError()
                expected += 1
        linked_rows = [row for row in chunk_rows if row[7] is not None]
        if linked_rows:
            if len(linked_rows) != len(chunk_rows):
                raise IndexVerificationError("MIXED_PARENT_INDEX_INVALID")
            parent_rows = await _rows(
                await _await(
                    self.connection.execute(
                        "SELECT document_version_id::text, parent_id::text, content, content_hash "
                        "FROM customer_service.document_parent "
                        "WHERE document_version_id = ANY(%s::uuid[])",
                        (list(member_versions),),
                    )
                )
            )
            parents_by_id = {str(row[1]): row for row in parent_rows}
            if not parents_by_id:
                raise IndexVerificationError()
            for row in linked_rows:
                parent = parents_by_id.get(str(row[7]))
                if (
                    parent is None
                    or str(parent[0]) != str(row[0])
                    or sha256(str(parent[2]).encode("utf-8")).hexdigest() != parent[3]
                    or str(parent[2])[row[9] : row[10]] != str(row[2])
                ):
                    raise IndexVerificationError()
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
