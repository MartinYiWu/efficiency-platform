"""智能客服文档分块与向量仓储契约测试。"""

from __future__ import annotations

from hashlib import sha256
from uuid import UUID

import pytest

from efficiency_platform_agent.agents.customer_service.chunking import (
    chunk_document,
    parent_child_document,
)
from efficiency_platform_agent.agents.customer_service.contracts import ParsedDocument
from efficiency_platform_agent.agents.customer_service.parsing import join_pages
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


def test_parent_child_keeps_complete_numbered_clause_and_exception() -> None:
    document = ParsedDocument(
        markdown=(
            "# 请假制度\n\n"
            "第一条 员工请假须提前申请。\n\n"
            "但紧急情况可在返岗后补交证明。\n\n"
            "第二条 主管应在两个工作日内审批。"
        )
    )

    parents = parent_child_document(
        document, child_max_tokens=20, child_overlap_tokens=4
    )

    assert len(parents) == 2
    assert parents[0].content == (
        "第一条 员工请假须提前申请。\n\n但紧急情况可在返岗后补交证明。"
    )
    assert parents[0].section_path == "请假制度"
    assert all(child.parent_no == 1 for child in parents[0].children)
    assert all(
        parents[0].content[child.start_offset : child.end_offset] == child.content
        for child in parents[0].children
    )
    assert "第二条" not in parents[0].content
    assert parents[1].content.startswith("第二条")


def test_parent_child_keeps_pdf_page_range_for_cross_page_clause() -> None:
    first = "第一条 员工出差前提交申请。\n\n"
    second = "紧急情况允许事后补交审批材料。"
    parents = parent_child_document(
        ParsedDocument(
            markdown=first + second,
            page_markers=((0, 1), (len(first), 2)),
        )
    )
    assert parents[0].page_start == 1
    assert parents[0].page_end == 2
    assert parents[0].children[0].page_no == 1


def test_cross_page_child_keeps_its_actual_start_page() -> None:
    first = "第一条 " + "申请前置条件。" * 5 + "\n\n"
    second = "跨页例外要求。" * 6
    parents = parent_child_document(
        ParsedDocument(
            markdown=first + second,
            page_markers=((0, 1), (len(first), 2)),
        ),
        child_max_tokens=20,
        child_overlap_tokens=2,
    )
    assert parents[0].page_start == 1
    assert parents[0].page_end == 2
    assert any(
        child.start_offset >= len(first) and child.page_no == 2
        for child in parents[0].children
    )


def test_join_pages_preserves_original_pdf_page_numbers() -> None:
    parsed = join_pages(("第一页", "", "第三页"))
    assert parsed["text"] == "第一页\n\n第三页"
    assert parsed["page_markers"] == ((0, 1), (len("第一页\n\n"), 3))


def test_join_pages_normalizes_newlines_before_recording_offsets() -> None:
    parsed = join_pages(("第一行\r\n第二行", "第二页"))
    assert parsed["text"] == "第一行\n第二行\n\n第二页"
    assert parsed["page_markers"] == ((0, 1), (len("第一行\n第二行\n\n"), 2))
    parents = parent_child_document(
        ParsedDocument(markdown=parsed["text"], page_markers=parsed["page_markers"])
    )
    assert parents[-1].page_start == 2


def test_large_table_splits_by_complete_rows_and_repeats_header() -> None:
    rows = "".join(f"| P{index} | 说明{index} |\n" for index in range(8))
    document = ParsedDocument(
        markdown="# 产品参数\n\n| 型号 | 说明 |\n|---|---|\n" + rows
    )

    parents = parent_child_document(
        document,
        parent_max_tokens=45,
        child_max_tokens=20,
        child_overlap_tokens=2,
    )

    assert len(parents) > 1
    assert all(
        parent.content.startswith("| 型号 | 说明 |\n|---|---|") for parent in parents
    )
    assert all(parent.content.count("| P") >= 1 for parent in parents)


def test_cross_page_table_groups_use_data_row_pages_for_children() -> None:
    header = "| 型号 | 说明 |\n|---|---|\n"
    first_rows = "".join(f"| A{index} | 第一页参数{index} |\n" for index in range(3))
    second_rows = "".join(f"| B{index} | 第二页参数{index} |\n" for index in range(3))
    markdown = header + first_rows + second_rows
    parents = parent_child_document(
        ParsedDocument(
            markdown=markdown,
            page_markers=((0, 1), (len(header + first_rows), 2)),
        ),
        parent_max_tokens=28,
        child_max_tokens=16,
        child_overlap_tokens=2,
    )

    second_page_groups = [parent for parent in parents if "| B0 |" in parent.content]
    assert second_page_groups
    assert second_page_groups[0].page_start == 2
    assert second_page_groups[0].page_end == 2
    assert all(child.page_no == 2 for child in second_page_groups[0].children)


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

    assert "DELETE FROM customer_service.document_chunk" in connection.calls[1][0]
    assert "INSERT INTO customer_service.document_chunk" in connection.calls[2][0]
    inserted = connection.calls[2][1][0]
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
async def test_replace_parent_child_chunks_writes_parent_before_children() -> None:
    connection = _Connection()
    repository = DocumentChunkRepository(connection)
    parents = parent_child_document(
        ParsedDocument(markdown="# 制度\n\n第一条 员工应提交申请。")
    )

    await repository.replace_version_chunks(
        tenant_id="dev",
        knowledge_base_id="11111111-1111-1111-1111-111111111111",
        document_id="22222222-2222-2222-2222-222222222222",
        document_version_id="33333333-3333-3333-3333-333333333333",
        document_title="测试文档",
        version_no=2,
        parents=parents,
        chunks=tuple(child for parent in parents for child in parent.children),
        embeddings=((0.0,) * 1024,),
    )

    statements = [sql for sql, _ in connection.calls]
    assert "DELETE FROM customer_service.document_chunk" in statements[1]
    assert "DELETE FROM customer_service.document_parent" in statements[2]
    assert "INSERT INTO customer_service.document_parent" in statements[3]
    assert "INSERT INTO customer_service.document_chunk" in statements[4]


@pytest.mark.asyncio
async def test_published_document_version_cannot_be_replaced_in_place() -> None:
    class Connection(_Connection):
        async def execute(self, sql, params=()):
            self.calls.append((sql, params))
            if "FROM customer_service.index_release_document" in sql:
                return _Result([(1,)])
            return _Result()

    connection = Connection()
    parents = parent_child_document(ParsedDocument(markdown="第一条 已发布制度。"))
    with pytest.raises(ValueError, match="PUBLISHED_DOCUMENT_VERSION_IMMUTABLE"):
        await DocumentChunkRepository(connection).replace_version_chunks(
            tenant_id="dev",
            knowledge_base_id="11111111-1111-1111-1111-111111111111",
            document_id="22222222-2222-2222-2222-222222222222",
            document_version_id="33333333-3333-3333-3333-333333333333",
            document_title="制度",
            version_no=1,
            parents=parents,
            chunks=parents[0].children,
            embeddings=((0.0,) * 1024,),
        )
    assert not any("DELETE FROM" in sql for sql, _ in connection.calls)


@pytest.mark.asyncio
async def test_get_parents_restricts_to_bound_index_version() -> None:
    class Connection(_Connection):
        async def execute(self, sql, params=()):
            self.calls.append((sql, params))
            return _Result(
                [
                    (
                        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "11111111-1111-1111-1111-111111111111",
                        "22222222-2222-2222-2222-222222222222",
                        "33333333-3333-3333-3333-333333333333",
                        "44444444-4444-4444-4444-444444444444",
                        "制度",
                        2,
                        "请假",
                        1,
                        2,
                        "完整条款",
                        sha256("完整条款".encode()).hexdigest(),
                        4,
                    )
                ]
            )

    connection = Connection()
    repository = DocumentChunkRepository(connection)
    parents = await repository.get_parents(
        tenant_id="dev",
        index_release_ids=(UUID("44444444-4444-4444-4444-444444444444"),),
        parent_ids=(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),),
    )

    assert parents[0].content == "完整条款"
    assert parents[0].page_no == 1
    assert parents[0].page_end == 2
    assert "index_release_document" in connection.calls[0][0]
    assert "p.tenant_id=%s" in connection.calls[0][0]


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
async def test_verify_release_rejects_mixed_parent_and_legacy_chunks() -> None:
    parent_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    version_id = "33333333-3333-3333-3333-333333333333"

    class Connection(_Connection):
        async def execute(self, sql, params=()):
            del params
            if "FROM customer_service.index_release_document" in sql:
                return _Result(
                    [("22222222-2222-2222-2222-222222222222", version_id, "a" * 64)]
                )
            if "FROM customer_service.document_chunk" in sql:
                return _Result(
                    [
                        (
                            version_id,
                            1,
                            "条款一",
                            sha256("条款一".encode()).hexdigest(),
                            "text-embedding-v4",
                            1024,
                            1024,
                            parent_id,
                            1,
                            0,
                            3,
                        ),
                        (
                            version_id,
                            2,
                            "旧片段",
                            sha256("旧片段".encode()).hexdigest(),
                            "text-embedding-v4",
                            1024,
                            1024,
                            None,
                            None,
                            None,
                            None,
                        ),
                    ]
                )
            if "FROM customer_service.document_parent" in sql:
                return _Result(
                    [
                        (
                            version_id,
                            parent_id,
                            "条款一",
                            sha256("条款一".encode()).hexdigest(),
                        )
                    ]
                )
            return _Result()

    with pytest.raises(IndexVerificationError):
        await DocumentChunkRepository(Connection()).verify_index_release(
            "44444444-4444-4444-4444-444444444444"
        )


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
