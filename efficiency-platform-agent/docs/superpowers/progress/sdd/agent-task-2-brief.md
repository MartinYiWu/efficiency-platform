### Task 2: 实现确定性展示验证、复制文本和 V1 投影

**Files:**
- Create: `src/efficiency_platform_agent/capabilities/quality/deliverable_v2.py`
- Modify: `src/efficiency_platform_agent/capabilities/quality/__init__.py`
- Create: `tests/unit/capabilities/quality/test_deliverable_v2.py`

**Interfaces:**
- Consumes: Task 1 的 `DeliverableSetV2`、`OperationDeliverableV2`、`CitationV2`。
- Produces: `DeliveryPresentationValidator.validate_deliverable()`、`assemble_set_v2()`、`render_copy_text()`、`project_set_v2_to_v1()`。

- [ ] **Step 1: 写引用闭包、排名和允许动作的失败测试**

```python
def test_validator_rejects_missing_citation_and_non_contiguous_rank() -> None:
    value = ranked_deliverable(items=[item(rank=1, refs=["missing"]), item(rank=3, refs=[])])
    with pytest.raises(ValueError, match="DELIVERY_CITATION_CLOSURE_INVALID"):
        DeliveryPresentationValidator().validate_deliverable(value)


def test_validator_rejects_unknown_next_action() -> None:
    with pytest.raises(ValidationError):
        NextActionV2(
            action_id="publish",
            action_type="publish_now",
            label="立即发布",
            target_deliverable_id="d-1",
            target_item_ids=[],
            intent_patch={},
            requires_user_input=False,
        )
```

- [ ] **Step 2: 写复制文本与 V1 投影的失败测试**

```python
def test_ranked_digest_copy_text_is_rendered_from_structured_items() -> None:
    value = ranked_deliverable(items=[item(rank=1, title="事件 A", summary="摘要 A")])
    assert render_copy_text(value).startswith("1. 事件 A")
    assert "摘要 A" in render_copy_text(value)


def test_v1_projection_keeps_citations_and_does_not_invent_v2_quality() -> None:
    projected = project_set_v2_to_v1(deliverable_set_v2())
    assert projected.contract_version == "deliverable-set/1"
    assert projected.deliverables[0].citations[0].url == "https://example.test/a"


def test_ranked_digest_requires_collection_window_and_ranking_basis() -> None:
    value = deliverable_set_v2(provenance=None)
    with pytest.raises(ValueError, match="DELIVERY_RESEARCH_PROVENANCE_REQUIRED"):
        assemble_set_v2(value)


def test_platform_bodies_cannot_be_copied_across_platforms() -> None:
    value = deliverable_set_v2(
        deliverables=[
            platform_deliverable("xiaohongshu", "同一正文"),
            platform_deliverable("wechat", "同一正文"),
        ]
    )
    with pytest.raises(ValueError, match="DELIVERY_PLATFORM_CONTENT_DUPLICATED"):
        assemble_set_v2(value)
```

- [ ] **Step 3: 运行目标测试并确认红灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/capabilities/quality/test_deliverable_v2.py -q
```

Expected: import FAIL，四个函数尚不存在。

- [ ] **Step 4: 实现验证器和复制文本渲染**

```python
_ALLOWED_ACTION_TYPES = {
    "rewrite_for_platform",
    "expand_item",
    "generate_script",
    "replace_candidates",
    "show_sources",
    "refine_constraints",
}

class DeliveryPresentationValidator:
    def validate_deliverable(self, value: OperationDeliverableV2) -> OperationDeliverableV2:
        citations = {item.citation_id for item in value.citations}
        if value.content.kind == "ranked_digest":
            ranks = [item.rank for item in value.content.items]
            if ranks != list(range(1, len(ranks) + 1)):
                raise ValueError("DELIVERY_RANK_INVALID")
            referenced = {ref for item in value.content.items for ref in item.source_refs}
            if not referenced.issubset(citations):
                raise ValueError("DELIVERY_CITATION_CLOSURE_INVALID")
        rendered = render_copy_text(value)
        if value.copy_text != rendered:
            value = value.model_copy(update={"copy_text": rendered})
        return value
```

`render_copy_text()` 必须分别处理五种 `content.kind`，使用固定标题、编号、换行和标签顺序；不得调用模型。`assemble_set_v2()` 必须校验交付物 ID 唯一、动作目标存在、`target_item_ids` 属于目标交付物，并由确定性输入构造 `degraded` 与 `warnings`。研究摘要还必须要求 `provenance.collection_window_start/end` 与明确 `ranking_basis`；多平台内容对标准化后的 `body_markdown` 求 SHA-256，同一次集合内不同平台正文哈希不得相同。

- [ ] **Step 5: 实现 V1 投影**

`project_set_v2_to_v1()` 将每个 V2 交付物转换为：

```python
DeliverableV1(
    platform=item.platform,
    title=item.title,
    body=item.copy_text,
    hashtags=(item.content.hashtags if item.content.kind == "platform_content" else []),
    format_notes=(item.content.format_notes if item.content.kind == "platform_content" else []),
    citations=[CitationV1(url=c.url, title=c.title, source=c.source) for c in item.citations],
    warnings=[warning.code for warning in item.warnings],
)
```

集合摘要使用 `summary.message`，降级使用 `set_v2.degraded`。投影不得根据正文猜测来源质量、热点排名或动作。

- [ ] **Step 6: 运行目标与 V1 回归测试**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/capabilities/quality/test_deliverable_v2.py tests/unit/capabilities/quality/test_deliverable_hashtags.py -q
```

Expected: PASS；V1 hashtags 归一化行为不变。

- [ ] **Step 7: 更新进度账本并保存文件快照清单**

记录验证规则、V1 投影边界和全部测试结果。

