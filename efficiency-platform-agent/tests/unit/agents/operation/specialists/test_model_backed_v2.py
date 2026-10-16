"""模型交付 V2 的严格生成、来源与预算边界。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidencePack,
    EvidenceQualityStatus,
    EvidenceRecord,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.agents.operation.definition import operation_agent_specs
from efficiency_platform_agent.agents.operation.specialists.model_backed import (
    ModelBackedOperationSpecialist,
    freeze,
    plain,
)
from efficiency_platform_agent.contracts.deliverables import (
    BrandPlanV1,
    OperationDeliverableV3,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    SupervisorTask,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness import operation_agent_factory
from efficiency_platform_agent.harness.referenced_content_model import (
    ReferencedContentModelRuntime,
)
from efficiency_platform_agent.prompts.runtime import PromptRuntime

SOURCE = {"url": "https://example.com/news", "title": "发布消息", "source": "发布者"}
CITATION_ID = "citation-" + hashlib.sha256(SOURCE["url"].encode()).hexdigest()[:20]
CONTENTS = {
    "ranked_digest": {
        "kind": "ranked_digest",
        "selection_summary": "按信息价值筛选",
        "ranking_basis": "importance",
        "items": [
            {
                "item_id": "item-1",
                "rank": 1,
                "title": "消息",
                "summary": "事实摘要",
                "why_it_matters": "运营意义",
                "source_refs": [CITATION_ID],
                "confidence": "low",
                "verification_status": "unverified",
            }
        ],
    },
    "platform_content": {"kind": "platform_content", "body_markdown": "独立正文"},
    "action_plan": {
        "kind": "action_plan",
        "goal": "目标",
        "audience": "受众",
        "phases": [{"phase_id": "phase-1", "title": "阶段", "actions": ["行动"]}],
    },
    "diagnosis": {
        "kind": "diagnosis",
        "findings": [
            {
                "finding_id": "finding-1",
                "title": "判断",
                "priority": "high",
                "recommendation": "建议",
            }
        ],
    },
    "retrospective": {
        "kind": "retrospective",
        "objectives": ["目标"],
        "next_steps": ["下一步"],
    },
}


def draft(kind: str = "ranked_digest") -> dict[str, Any]:
    """创建只包含模型可写字段的合成草稿。"""
    return {
        "contract_version": "deliverable/2",
        "deliverable_id": "delivery-1",
        "platform": "research" if kind == "ranked_digest" else "wechat",
        "title": "成品",
        "lead": "导语",
        "deliverable_kind": kind,
        "content": json.loads(json.dumps(CONTENTS[kind])),
        "citations": [],
        "copy_text": "",
        "warnings": [],
    }


class RecordingModel:
    """记录窄模型端口请求并返回有真实字段形状的离线响应。"""

    def __init__(self, *outputs: Any) -> None:
        self.outputs = list(outputs)
        self.requests: list[Any] = []
        self.demands: list[Any] = []
        self.budgets: list[Any] = []

    async def complete(
        self, demand: Any, request: Any, *, remaining_budget: Any
    ) -> Any:
        self.demands.append(demand)
        self.requests.append(request)
        self.budgets.append(remaining_budget)
        output = self.outputs.pop(0)
        error = output if isinstance(output, SimpleNamespace) else None
        return SimpleNamespace(
            result=SimpleNamespace(
                error=error,
                message=None
                if error
                else (
                    output
                    if isinstance(output, ProviderMessage)
                    else ProviderMessage("assistant", json.dumps(output))
                ),
            ),
            usage=UsageSnapshot(input_tokens=10, output_tokens=20, cost_microunits=1),
            attempts=("attempt",),
            degraded=False,
        )


def task(
    capability: str = "operation.research.insight",
    *,
    iterations: int = 4,
    platform: str | None = None,
    input_deliverables: list[dict[str, Any]] | None = None,
) -> SupervisorTask:
    """创建已有 Supervisor 外壳中的最小输入。"""
    value = freeze(
        {
            "platform": platform
            or (
                "research"
                if capability.endswith("research.insight")
                else "wechat"
            ),
            "tenant_id": "tenant-1",
            "goal": "生成内容",
            "task_id": "task-1",
            "plan_id": "plan-1",
            "deliverable_id": "delivery-1",
            "citations": [SOURCE],
            "input_deliverables": input_deliverables or [],
            "profile_reference_ids": [],
            "research": capability.endswith("research.insight"),
        }
    )
    assert isinstance(value, JsonObject)
    return SupervisorTask(
        "task-1",
        "run-1",
        capability,
        value,
        JsonObject(),
        frozenset(),
        ExecutionBudget(iterations, 0, 10000, 1000, 30000, 10000),
    )


def specialist(
    model: Any, capability: str = "operation.research.insight", **kwargs: Any
) -> Any:
    """通过正式注册的 Prompt 和已有 AgentSpec 构造专家。"""
    registry = operation_agent_factory.build_operation_prompt_registry()
    spec = next(item for item in operation_agent_specs() if item.agent_id == capability)
    kwargs.setdefault("deliverable_contract_version", "deliverable/2")
    return ModelBackedOperationSpecialist(
        spec, PromptRuntime(registry), model, **kwargs
    )


def payload(result: Any) -> dict[str, Any]:
    return plain(result.output)["deliverable_bundle"]["deliverables"][0]["payload"]


@pytest.mark.asyncio
async def test_v3_specialist_delegates_to_scenario_executor_without_generic_prompt() -> None:
    class ScenarioExecutor:
        def __init__(self) -> None:
            self.calls = []

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            content = BrandPlanV1(
                current_context=["冷启动"],
                objectives=["建立认知"],
                positioning="效率工具",
                audience_segments=[{"name": "运营负责人"}],
                value_proposition=["提升效率"],
                content_pillars=[{"name": "实战"}],
                channel_strategy=[{"channel": "公众号"}],
                roadmap=[{"phase": "验证"}],
                metric_framework=[
                    {
                        "name": "互动率",
                        "definition": "互动/曝光",
                        "observation_period": "每周",
                        "purpose": "评估内容",
                    }
                ],
                next_actions=["访谈用户"],
            )
            return OperationDeliverableV3(
                deliverable_id="temporary",
                scenario="brand_operation_plan",
                title="品牌方案",
                copy_text="# 品牌方案",
                content=content,
            )

    executor = ScenarioExecutor()
    model = RecordingModel()
    result = await specialist(
        model,
        "operation.brand.strategy",
        deliverable_contract_version="deliverable/3",
        scenario_executor=executor,
    ).run(task("operation.brand.strategy"))

    result_payload = payload(result)
    assert model.requests == []
    assert executor.calls[0]["scenario"] == "brand_operation_plan"
    assert result_payload["deliverable_id"] == "delivery-1"
    assert result_payload["content"]["kind"] == "brand_plan"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability", "kind"),
    [
        ("operation.research.insight", "ranked_digest"),
        ("operation.content.create", "platform_content"),
        ("operation.campaign.plan", "action_plan"),
        ("operation.quality.review", "diagnosis"),
        ("operation.analytics.review", "retrospective"),
    ],
)
async def test_v2_uses_specific_draft_schema_and_returns_formal_payload(
    capability: str, kind: str
) -> None:
    model = RecordingModel(draft(kind))
    result = payload(await specialist(model, capability).run(task(capability)))
    schema = plain(model.requests[0].options)["response_format"]["json_schema"]
    assert schema["name"] == "operation_" + kind
    assert schema["schema"]["properties"]["copy_text"]["const"] == ""
    trusted_schema = json.loads(
        model.requests[0].messages[-2].content.split("：", 1)[1]
    )
    assert trusted_schema["authority_fields"]["deliverable_kind"] == kind
    assert trusted_schema["output_schema"]["additionalProperties"] is False
    assert result["contract_version"] == "deliverable/2"
    assert result["content"]["kind"] == kind
    assert result["copy_text"]
    assert result["citations"][0]["citation_id"] == CITATION_ID
    assert result["citations"][0]["verification_status"] == "unverified"
    assert result["citations"][0]["source_type"] == "public_page"
    assert result["citations"][0]["source_tier"] == "secondary"
    assert result["citations"][0]["independent_source_group"] == "example.com"
    assert result["citations"][0]["supports_item_ids"] == (
        ["item-1"] if kind == "ranked_digest" else []
    )


@pytest.mark.asyncio
async def test_model_demand_estimates_tokens_instead_of_counting_characters() -> None:
    model = RecordingModel(draft("action_plan"))
    await specialist(model, "operation.campaign.plan").run(
        task("operation.campaign.plan")
    )
    request_chars = sum(len(message.content) for message in model.requests[0].messages)
    assert model.demands[0].estimated_input_tokens <= (request_chars + 3) // 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "deliverable/1"),
        ("platform", "other"),
        ("deliverable_id", "other"),
        ("citations", [{"url": "https://evil.example"}]),
        ("permissions", ["admin"]),
    ],
)
async def test_authority_errors_never_trigger_repair(field: str, value: Any) -> None:
    bad = draft()
    bad[field] = value
    bad["title"] = ""
    model = RecordingModel(bad, draft())
    with pytest.raises(ValueError):
        await specialist(model).run(task())
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_unknown_source_ref_never_triggers_repair() -> None:
    bad = draft()
    bad["content"]["items"][0]["source_refs"] = ["unknown"]
    bad["title"] = ""
    model = RecordingModel(bad, draft())
    with pytest.raises(ValueError, match="CITATION"):
        await specialist(model).run(task())
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_structural_repair_occurs_once_with_remaining_budget() -> None:
    bad = draft()
    bad["title"] = ""
    model = RecordingModel(bad, draft())
    assert payload(await specialist(model).run(task()))["copy_text"]
    assert len(model.requests) == 2
    assert model.budgets[1].iterations == 3
    assert model.budgets[1].input_tokens == 9990
    assert model.budgets[1].output_tokens == 980
    assert model.budgets[1].cost_microunits == 9999
    assert plain(model.requests[1].options)["max_tokens"] == 980


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_output", [{}])
async def test_failed_repair_never_makes_third_request(repair_output: Any) -> None:
    model = RecordingModel({}, repair_output, draft())
    with pytest.raises(ValueError):
        await specialist(model).run(task())
    assert len(model.requests) == 2


@pytest.mark.asyncio
async def test_exhausted_iterations_prevent_repair() -> None:
    model = RecordingModel({}, draft())
    with pytest.raises(ValueError):
        await specialist(model).run(task(iterations=1))
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_runtime_warnings_are_structured() -> None:
    model = RecordingModel(draft())
    result = payload(
        await specialist(model, extra_warnings=("EVIDENCE_UNVERIFIED",)).run(task())
    )
    assert result["warnings"][0]["code"] == "EVIDENCE_UNVERIFIED"
    assert result["warnings"][0]["message"]


@pytest.mark.asyncio
async def test_explicit_v1_still_uses_v1_contract_and_prompt() -> None:
    old = {
        "contract_version": "deliverable/1",
        "platform": "research",
        "title": "成品",
        "body": "正文",
        "citations": [SOURCE],
    }
    model = RecordingModel(old)
    result = payload(
        await specialist(model, deliverable_contract_version="deliverable/1").run(
            task()
        )
    )
    assert result["contract_version"] == "deliverable/1"
    assert (
        plain(model.requests[0].options)["response_format"]["json_schema"]["name"]
        == "operation_deliverable"
    )


@pytest.mark.asyncio
async def test_wrong_target_fails_before_model_call() -> None:
    model = RecordingModel(draft())
    with pytest.raises(ValueError):
        await specialist(model).run(replace(task(), target_agent="other"))
    assert not model.requests


@pytest.mark.asyncio
async def test_model_cannot_claim_verified_research_item_even_with_structural_error() -> (
    None
):
    bad = draft()
    bad["content"]["items"][0]["verification_status"] = "verified"
    bad["title"] = ""
    model = RecordingModel(bad, draft())
    with pytest.raises(ValueError):
        await specialist(model).run(task())
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_rank_type_is_strict_and_repaired_once() -> None:
    bad = draft()
    bad["content"]["items"][0]["rank"] = "1"
    model = RecordingModel(bad, draft())
    await specialist(model).run(task())
    assert len(model.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "budget",
    [
        ExecutionBudget(4, 0, 10, 1000, 30000, 10000),
        ExecutionBudget(4, 0, 10000, 20, 30000, 10000),
        ExecutionBudget(4, 0, 10000, 1000, 30000, 1),
    ],
)
async def test_other_exhausted_budgets_prevent_repair(budget: ExecutionBudget) -> None:
    model = RecordingModel({}, draft())
    with pytest.raises(ValueError):
        await specialist(model).run(replace(task(), budget=budget))
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_pack_id_and_date_are_preserved_without_upgrading_verification() -> None:
    pack = EvidencePack(
        "evidence-pack/1",
        "pack-1",
        "task-1",
        (
            EvidenceRecord(
                "evidence-1",
                "原始标题",
                "原始发布者",
                SOURCE["url"],
                1_789_520_400_000,
                1_789_610_400_000,
                SourceScope.EXTERNAL_REFERENCE,
                frozenset({"goal"}),
                True,
                EvidenceDuplicateStatus.UNIQUE,
                EvidenceQualityStatus.VALID,
            ),
        ),
        (),
    )
    value = draft()
    value["content"]["items"][0]["source_refs"] = ["evidence-1"]
    model = RecordingModel(value)
    result = payload(await specialist(model, evidence_pack=pack).run(task()))
    citation = result["citations"][0]
    assert citation["citation_id"] == "evidence-1"
    assert citation["published_at"].endswith("+00:00")
    assert citation["verification_status"] == "unverified"
    assert citation["supports_item_ids"] == ["item-1"]


@pytest.mark.asyncio
async def test_explicit_v1_unknown_url_is_not_repaired_even_if_title_invalid() -> None:
    bad = {
        "contract_version": "deliverable/1",
        "platform": "research",
        "title": "",
        "body": "正文",
        "citations": [{"url": "https://evil.example"}],
    }
    model = RecordingModel(bad, bad)
    with pytest.raises(ValueError):
        await specialist(model, deliverable_contract_version="deliverable/1").run(
            task()
        )
    assert len(model.requests) == 1


@pytest.mark.asyncio
async def test_default_stays_v1_until_aggregation_migrates() -> None:
    old = {
        "contract_version": "deliverable/1",
        "platform": "research",
        "title": "成品",
        "body": "正文",
        "citations": [SOURCE],
    }
    model: Any = RecordingModel(old)
    spec = next(
        item
        for item in operation_agent_specs()
        if item.agent_id == "operation.research.insight"
    )
    runtime = PromptRuntime(operation_agent_factory.build_operation_prompt_registry())
    result = payload(
        await ModelBackedOperationSpecialist(spec, runtime, model).run(task())
    )
    assert result["contract_version"] == "deliverable/1"


@pytest.mark.asyncio
async def test_truncated_repair_gets_one_same_prompt_transport_retry() -> None:
    model = RecordingModel(
        {}, SimpleNamespace(code="PROVIDER_RESPONSE_TRUNCATED"), draft()
    )
    result = payload(await specialist(model).run(task()))
    assert result["contract_version"] == "deliverable/2"
    assert len(model.requests) == 3
    assert model.requests[1].messages == model.requests[2].messages
    assert model.budgets[2].iterations == 2
    assert model.budgets[2].input_tokens == 9980
    assert model.budgets[2].output_tokens == 960
    assert model.budgets[2].cost_microunits == 9998


@pytest.mark.asyncio
async def test_truncated_repair_with_exhausted_iterations_has_no_transport_retry() -> (
    None
):
    model = RecordingModel(
        {}, SimpleNamespace(code="PROVIDER_RESPONSE_TRUNCATED"), draft()
    )
    with pytest.raises(ValueError):
        await specialist(model).run(task(iterations=2))
    assert len(model.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("with_pack", [True, False])
async def test_path_trailing_slash_preserves_distinct_citation_records(
    with_pack: bool,
) -> None:
    """带查询参数的不同路径不得被合并或混用来源记录。"""
    sources = [
        {
            "url": "https://example.com/news/?id=1",
            "title": "Article A",
            "source": "Publisher A",
        },
        {
            "url": "https://example.com/news?id=1",
            "title": "Article B",
            "source": "Publisher B",
        },
    ]
    records = tuple(
        EvidenceRecord(
            f"evidence-{suffix}",
            source["title"],
            source["source"],
            source["url"],
            1_789_520_400_000 + index * 86_400_000,
            1_789_710_400_000,
            SourceScope.EXTERNAL_REFERENCE,
            frozenset({"goal"}),
            True,
            EvidenceDuplicateStatus.UNIQUE,
            EvidenceQualityStatus.VALID,
        )
        for index, (suffix, source) in enumerate(zip(("a", "b"), sources, strict=True))
    )
    pack = (
        EvidencePack("evidence-pack/1", "pack-1", "task-1", records, ())
        if with_pack
        else None
    )
    original = task("operation.content.create")
    raw = plain(original.input_data)
    raw["citations"] = sources
    frozen = freeze(raw)
    assert isinstance(frozen, JsonObject)
    model = RecordingModel(draft("platform_content"))
    result = payload(
        await specialist(model, "operation.content.create", evidence_pack=pack).run(
            replace(original, input_data=frozen)
        )
    )
    citations = result["citations"]
    assert len(citations) == 2
    for citation, source, record in zip(citations, sources, records, strict=True):
        assert (citation["url"], citation["title"], citation["source"]) == (
            source["url"],
            source["title"],
            source["source"],
        )
        assert citation["citation_id"] == (
            record.evidence_id
            if with_pack
            else "citation-" + hashlib.sha256(source["url"].encode()).hexdigest()[:20]
        )
        assert citation["published_at"] == (
            datetime.fromtimestamp(
                record.published_at_epoch_ms / 1000, tz=UTC
            ).isoformat()
            if with_pack and record.published_at_epoch_ms is not None
            else None
        )


@pytest.mark.asyncio
async def test_evidence_metadata_is_selected_as_one_record() -> None:
    """有匹配证据时标题、发布者、ID 和日期来自同一证据记录。"""
    record = EvidenceRecord(
        "evidence-a",
        "证据原始标题",
        "证据原始发布者",
        SOURCE["url"],
        1_789_520_400_000,
        1_789_610_400_000,
        SourceScope.EXTERNAL_REFERENCE,
        frozenset({"goal"}),
        True,
        EvidenceDuplicateStatus.UNIQUE,
        EvidenceQualityStatus.VALID,
    )
    pack = EvidencePack("evidence-pack/1", "pack-1", "task-1", (record,), ())
    model = RecordingModel(draft("platform_content"))
    result = payload(
        await specialist(model, "operation.content.create", evidence_pack=pack).run(
            task("operation.content.create")
        )
    )
    citation = result["citations"][0]
    assert (
        citation["title"],
        citation["source"],
        citation["citation_id"],
        citation["published_at"],
    ) == (
        record.title,
        record.publisher,
        record.evidence_id,
        datetime.fromtimestamp(1_789_520_400_000 / 1000, tz=UTC).isoformat(),
    )


def _wechat_draft(chinese_characters: int) -> dict[str, Any]:
    value = draft("platform_content")
    value["platform"] = "wechat_official_account"
    value["content"]["body_markdown"] = "\n\n".join(
        (
            "# 本周人工智能行业观察",
            "导语说明本周值得关注的人工智能动态。",
            "## 一、事实与变化",
            "**事实**：",
            "这" * (chinese_characters // 2),
            "**影响**：",
            "人" * (chinese_characters - chinese_characters // 2),
            "**运营观察**：应继续追踪已核验来源。",
            "## 收束",
            "以上判断以现有证据为边界。",
        )
    )
    return value


def _structured_wechat_rewrite(hotspot_count: int) -> dict[str, Any]:
    return {
        "introduction": "导" * 240,
        "hotspots": [
            {
                "fact": "事" * 1_000,
                "impact": "影" * 1_000,
                "operation_observation": "运" * 1_000,
            }
            for _ in range(hotspot_count)
        ],
        "closing": "收" * 240,
    }


@pytest.mark.asyncio
async def test_trailing_model_text_is_removed_before_strict_validation() -> None:
    raw = json.dumps(_wechat_draft(3200), ensure_ascii=False) + "\n尾随解释不得进入交付物"
    model = RecordingModel(ProviderMessage("assistant", raw))

    result = payload(
        await specialist(model, "operation.content.create").run(
            task("operation.content.create", platform="wechat_official_account")
        )
    )

    assert len(model.requests) == 1
    assert "尾随解释" not in result["content"]["body_markdown"]


@pytest.mark.asyncio
async def test_wechat_quality_failure_is_repaired_once_with_structured_schema() -> None:
    model = RecordingModel(
        _wechat_draft(200),
        {
            "background_and_impact": ["背" * 220] * 5,
            "content_strategy": ["策" * 220] * 5,
            "action_guidance": ["行" * 220] * 5,
        },
    )
    result = payload(
        await specialist(model, "operation.content.create").run(
            task(
                "operation.content.create",
                platform="wechat_official_account",
                input_deliverables=[{"item_id": f"item-{index}"} for index in range(3)],
            )
        )
    )

    assert len(model.requests) == 2
    assert "wechat_supplement" in json.dumps(
        plain(model.requests[1].options), ensure_ascii=False
    )
    assert "只补写公众号文章" in model.requests[1].messages[0].content
    assert "顶层只能包含 background_and_impact、content_strategy、action_guidance" in (
        model.requests[1].messages[0].content
    )
    assert "每个字段固定写 5 个自然段" in model.requests[1].messages[0].content
    assert '"required"' not in model.requests[1].messages[0].content
    assert "仅长度不足" in model.requests[1].messages[-1].content
    assert model.demands[0].requested_tier.value == "balanced"
    assert result["platform"] == "wechat_official_account"


@pytest.mark.asyncio
async def test_wechat_length_failure_uses_one_structured_supplement_repair() -> None:
    model = RecordingModel(
        _wechat_draft(2_400),
        {
            "background_and_impact": ["背" * 120] * 2,
            "content_strategy": ["策" * 120] * 2,
            "action_guidance": ["行" * 120] * 2,
            "action_guidance_note": "模型额外解释不会进入文章",
        },
    )
    run_task = task(
        "operation.content.create",
        platform="wechat_official_account",
        input_deliverables=[{"item_id": f"item-{index}"} for index in range(3)],
    )
    run_task = replace(
        run_task,
        budget=ExecutionBudget(4, 0, 24_000, 24_000, 180_000, 30_000),
    )

    result = payload(await specialist(model, "operation.content.create").run(run_task))

    assert len(model.requests) == 2
    assert "wechat_supplement" in json.dumps(
        plain(model.requests[1].options), ensure_ascii=False
    )
    assert "每个字段固定写 2 个自然段" in (
        model.requests[1].messages[0].content
    )
    assert "运营背景与影响" in result["content"]["body_markdown"]


@pytest.mark.asyncio
async def test_wechat_length_repair_rewrites_when_hotspot_structure_is_missing() -> None:
    invalid = _wechat_draft(1_200)
    invalid["content"]["body_markdown"] = "\n\n".join(
        (
            "# 本周人工智能行业观察",
            "## 热点一",
            "原" * 1_200,
            "## 结语",
            "以上为本周观察。",
        )
    )
    model = RecordingModel(invalid, _structured_wechat_rewrite(1))

    result = payload(
        await specialist(model, "operation.content.create").run(
            task("operation.content.create", platform="wechat_official_account")
        )
    )

    assert len(model.requests) == 2
    repair_options = json.dumps(plain(model.requests[1].options), ensure_ascii=False)
    assert "wechat_structured_rewrite" in repair_options
    assert "wechat_supplement" not in repair_options
    assert "只输出 introduction、hotspots、closing 三个字段" in "\n".join(
        message.content for message in model.requests[1].messages
    )
    assert result["platform"] == "wechat_official_account"
    assert "**事实**" in result["content"]["body_markdown"]


@pytest.mark.asyncio
async def test_wechat_structured_repair_retries_with_the_same_json_shape_when_short() -> None:
    invalid = _wechat_draft(1_200)
    invalid["content"]["body_markdown"] = "\n\n".join(
        ("# 本周人工智能行业观察", "## 热点一", "原" * 1_200, "## 结语")
    )
    short_rewrite = _structured_wechat_rewrite(1)
    short_rewrite["introduction"] = "导" * 30
    short_rewrite["hotspots"][0] = {
        "fact": "事" * 30,
        "impact": "影" * 30,
        "operation_observation": "运" * 30,
    }
    short_rewrite["closing"] = "收" * 30
    model = RecordingModel(invalid, short_rewrite, _structured_wechat_rewrite(1))

    result = payload(
        await specialist(model, "operation.content.create").run(
            task("operation.content.create", platform="wechat_official_account")
        )
    )

    assert len(model.requests) == 3
    assert "上一版结构化改写的内容太短" in model.requests[2].messages[0].content
    retry_options = json.dumps(plain(model.requests[2].options), ensure_ascii=False)
    assert "wechat_structured_rewrite" in retry_options
    body = result["content"]["body_markdown"]
    assert len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", body)) >= 3_000


@pytest.mark.asyncio
async def test_wechat_supplement_is_the_only_semantic_repair() -> None:
    model = RecordingModel(
        _wechat_draft(2_500),
        {
            "background_and_impact": ["背" * 100] * 2,
            "content_strategy": ["策" * 100] * 2,
            "action_guidance": ["行" * 100] * 2,
        },
    )
    run_task = task(
        "operation.content.create",
        platform="wechat_official_account",
        input_deliverables=[{"item_id": f"item-{index}"} for index in range(3)],
    )
    run_task = replace(
        run_task,
        budget=ExecutionBudget(4, 0, 24_000, 24_000, 180_000, 30_000),
    )

    result = payload(await specialist(model, "operation.content.create").run(run_task))

    assert len(model.requests) == 2
    assert "内容选题方法" in result["content"]["body_markdown"]
    assert "行动启示" in result["content"]["body_markdown"]


@pytest.mark.asyncio
async def test_wechat_near_minimum_length_uses_one_paragraph_without_overshoot() -> None:
    model = RecordingModel(
        _wechat_draft(2_900),
        {
            "background_and_impact": ["背" * 100],
            "content_strategy": ["策" * 100],
            "action_guidance": ["行" * 100],
        },
    )

    result = payload(
        await specialist(model, "operation.content.create").run(
            task("operation.content.create", platform="wechat_official_account")
        )
    )

    assert "每个字段固定写 1 个自然段" in model.requests[1].messages[0].content
    body = result["content"]["body_markdown"]
    assert len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", body)) <= 4_000


@pytest.mark.asyncio
async def test_xiaohongshu_requires_three_paragraphs_and_five_to_ten_hashtags() -> None:
    invalid = draft("platform_content")
    invalid["platform"] = "xiaohongshu"
    invalid["content"].update(body_markdown="只有一段", hashtags=["#AI"])
    valid = draft("platform_content")
    valid["platform"] = "xiaohongshu"
    valid["content"].update(
        body_markdown="第一段\n\n第二段\n\n第三段",
        hashtags=["#AI", "#人工智能", "#科技", "#产品", "#运营"],
    )
    model = RecordingModel(invalid, valid)

    result = payload(
        await specialist(model, "operation.content.create").run(
            task("operation.content.create", platform="xiaohongshu")
        )
    )

    assert len(model.requests) == 2
    assert len(result["content"]["hashtags"]) == 5


@pytest.mark.asyncio
async def test_referenced_content_runtime_always_delegates_to_model() -> None:
    output = _wechat_draft(3200)
    delegate = RecordingModel(output)
    runtime = ReferencedContentModelRuntime(delegate)
    request = ProviderRequest(
        "operation-model/1",
        (
            ProviderMessage(
                "user",
                json.dumps(
                    {
                        "platform": "wechat_official_account",
                        "input_deliverables": [{"item": {"item_id": "item-1"}}],
                    }
                ),
            ),
            ProviderMessage(
                "user",
                json.dumps({"content": {"body_markdown": "上一版待修草稿"}}),
            ),
        ),
        JsonObject(),
        30_000,
    )

    result = await runtime.complete(None, request, remaining_budget=None)

    assert result.result.message is not None
    assert len(delegate.requests) == 1
    assert plain(delegate.requests[0].options)["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_referenced_content_keeps_provider_usage_below_run_output_budget() -> None:
    output = _wechat_draft(3200)
    model = RecordingModel(output)
    referenced_task = replace(
        task(
            "operation.channel.content",
            platform="wechat_official_account",
            input_deliverables=[{"item": {"item_id": "item-1"}}],
        ),
        budget=ExecutionBudget(4, 0, 20_000, 8_000, 90_000, 100_000),
    )

    await specialist(model, "operation.channel.content").run(referenced_task)

    assert plain(model.requests[0].options)["max_tokens"] == 7_500
    assert model.demands[0].max_output_tokens == 7_500
    assert model.budgets[0].output_tokens == 8_000
