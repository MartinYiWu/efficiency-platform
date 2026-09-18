"""模型交付 V2 的严格生成、来源与预算边界。"""

from __future__ import annotations

import hashlib
import json
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
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    SupervisorTask,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.harness import operation_agent_factory
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
        self.budgets: list[Any] = []

    async def complete(
        self, demand: Any, request: Any, *, remaining_budget: Any
    ) -> Any:
        self.requests.append(request)
        self.budgets.append(remaining_budget)
        output = self.outputs.pop(0)
        error = output if isinstance(output, SimpleNamespace) else None
        return SimpleNamespace(
            result=SimpleNamespace(
                error=error,
                message=None
                if error
                else ProviderMessage("assistant", json.dumps(output)),
            ),
            usage=UsageSnapshot(input_tokens=10, output_tokens=20, cost_microunits=1),
            attempts=("attempt",),
            degraded=False,
        )


def task(
    capability: str = "operation.research.insight", *, iterations: int = 4
) -> SupervisorTask:
    """创建已有 Supervisor 外壳中的最小输入。"""
    value = freeze(
        {
            "platform": "research"
            if capability.endswith("research.insight")
            else "wechat",
            "tenant_id": "tenant-1",
            "goal": "生成内容",
            "task_id": "task-1",
            "plan_id": "plan-1",
            "deliverable_id": "delivery-1",
            "citations": [SOURCE],
            "input_deliverables": [],
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
