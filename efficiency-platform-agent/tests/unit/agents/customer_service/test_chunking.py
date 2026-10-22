"""智能客服文档分块与向量仓储契约测试。"""

from __future__ import annotations

from hashlib import sha256

import pytest

from efficiency_platform_agent.agents.customer_service.chunking import chunk_document
from efficiency_platform_agent.agents.customer_service.contracts import ParsedDocument
from efficiency_platform_agent.agents.customer_service.vector_repository import (
    DocumentChunkRepository,
    IndexVerificationError,
)
from efficiency_platform_agent.providers.embedding.dashscope import (
    DashScopeEmbeddingProvider,
    EmbeddingProviderError,
)


def test_chunking_preserves_heading_path_and_bounds() -> None:
    document = ParsedDocument(
        markdown="# 公司制度\n\n## 请假流程\n\n" + "申请人提交审批。" * 30,
        page_markers=(),
    )

    chunks = chunk_document(document, max_tokens=40, overlap_tokens=8)

    assert len(chunks) > 1
    assert all(item.token_count <= 40 for item in chunks)
    assert all(item.section_path == "公司制度 / 请假流程" for item in chunks)
    assert chunks[0].content != chunks[1].content


def test_table_split_repeats_header() -> None:
    document = ParsedDocument(
        markdown=(
            "# 产品参数\n\n"
            "| 型号 | 说明 |\n|---|---|\n"
            + "".join(f"| P{index} | 参数说明{index} |\n" for index in range(12))
        ),
        page_markers=(),
    )

    chunks = chunk_document(document, max_tokens=28, overlap_tokens=4)
    table_chunks = [item for item in chunks if "| 型号 | 说明 |" in item.content]

    assert len(table_chunks) > 1
    assert all("|---|---|" in item.content for item in table_chunks)


class _Result:
    def __init__(self, rows=(), rowcount: int = 1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    async def fetchall(self):
        return self._rows


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def transaction(self):
        return _Transaction()

    async def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _Result()

    async def executemany(self, sql, params):
        self.calls.append((sql, tuple(params)))
        return _Result(rowcount=len(tuple(params)))


@pytest.mark.asyncio
async def test_replace_chunks_is_one_transaction_and_validates_dimension() -> None:
    connection = _Connection()
    repository = DocumentChunkRepository(connection)
    document = ParsedDocument(markdown="# 标题\n\n正文", page_markers=())
    chunk = chunk_document(document)[0]

    await repository.replace_version_chunks(
        tenant_id="dev",
        knowledge_base_id="11111111-1111-1111-1111-111111111111",
        document_id="22222222-2222-2222-2222-222222222222",
        document_version_id="33333333-3333-3333-3333-333333333333",
        document_title="测试文档",
        version_no=2,
        chunks=(chunk,),
        embeddings=((0.0,) * 1024,),
    )

    assert "DELETE FROM customer_service.document_chunk" in connection.calls[0][0]
    assert "INSERT INTO customer_service.document_chunk" in connection.calls[1][0]
    inserted = connection.calls[1][1][0]
    assert inserted[5:7] == ("测试文档", 2)

    with pytest.raises(ValueError, match="EMBEDDING_DIMENSION_INVALID"):
        await repository.replace_version_chunks(
            tenant_id="dev",
            knowledge_base_id="11111111-1111-1111-1111-111111111111",
            document_id="22222222-2222-2222-2222-222222222222",
            document_version_id="33333333-3333-3333-3333-333333333333",
            document_title="测试文档",
            version_no=2,
            chunks=(chunk,),
            embeddings=((0.0,) * 3,),
        )


@pytest.mark.asyncio
async def test_verify_release_rejects_missing_or_corrupt_chunks() -> None:
    class Connection(_Connection):
        async def execute(self, sql, params=()):
            del params
            if "index_release_document" in sql:
                return _Result(
                    [
                        (
                            "22222222-2222-2222-2222-222222222222",
                            "33333333-3333-3333-3333-333333333333",
                            "a" * 64,
                        )
                    ]
                )
            return _Result([])

    repository = DocumentChunkRepository(Connection())

    with pytest.raises(IndexVerificationError, match="KB_INDEX_VERIFY_FAILED"):
        await repository.verify_index_release("44444444-4444-4444-4444-444444444444")

    assert sha256(b"").hexdigest() != "a" * 64


@pytest.mark.asyncio
async def test_embedding_provider_validates_return_count_and_dimension() -> None:
    class Item:
        def __init__(self, index, embedding):
            self.index = index
            self.embedding = embedding

    class Embeddings:
        async def create(self, **_kwargs):
            return type("Response", (), {"data": [Item(0, [0.0] * 1024)]})()

    provider = DashScopeEmbeddingProvider(
        type("Client", (), {"embeddings": Embeddings()})()
    )

    assert len((await provider.embed(("制度",)))[0]) == 1024

    with pytest.raises(EmbeddingProviderError, match="数量"):
        await provider.embed(("制度", "流程"))


@pytest.mark.asyncio
async def test_embedding_provider_sends_at_most_ten_inputs_per_request() -> None:
    class Embeddings:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        async def create(self, **kwargs):
            inputs = kwargs["input"]
            if len(inputs) > 10:
                raise ValueError("batch size is invalid")
            self.calls.append(inputs)
            rows = [
                type(
                    "Item",
                    (),
                    {"index": index, "embedding": [float(text[5:])] + [0.0] * 1023},
                )()
                for index, text in reversed(tuple(enumerate(inputs)))
            ]
            return type("Response", (), {"data": rows})()

    client = type("Client", (), {"embeddings": Embeddings()})()
    provider = DashScopeEmbeddingProvider(client)

    vectors = await provider.embed(tuple(f"part-{index}" for index in range(14)))

    assert [len(call) for call in client.embeddings.calls] == [10, 4]
    assert [vector[0] for vector in vectors] == [float(index) for index in range(14)]
