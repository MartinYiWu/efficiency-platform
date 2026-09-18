### Task 1: 冻结 Deliverable V2 契约与交付类型映射

**Files:**
- Modify: `src/efficiency_platform_agent/contracts/deliverables.py`
- Create: `src/efficiency_platform_agent/agents/operation/delivery_kind.py`
- Create: `tests/contracts/test_deliverable_v2_contracts.py`
- Create: `tests/unit/agents/operation/test_delivery_kind.py`
- Create: `docs/superpowers/progress/2026-09-17-运营Agent专业化交付与质量闭环-进度.md`

**Interfaces:**
- Consumes: `OperationSpecialistCapabilityId` from `agents.operation.definition`。
- Produces: `OperationDeliverableV2` 判别联合、`DeliverableSetV2`、`DeliverableSet = DeliverableSetV1 | DeliverableSetV2`、`deliverable_kind_for(capability_id, platform, research)`。

- [ ] **Step 1: 写交付类型映射的失败测试**

```python
from efficiency_platform_agent.agents.operation.delivery_kind import (
    deliverable_kind_for,
)


def test_specialist_capability_maps_to_stable_delivery_kind() -> None:
    assert deliverable_kind_for("operation.research.insight", "research", True) == "ranked_digest"
    assert deliverable_kind_for("operation.channel.content", "xiaohongshu", False) == "platform_content"
    assert deliverable_kind_for("operation.campaign.plan", "活动策划", False) == "action_plan"
    assert deliverable_kind_for("operation.quality.review", "内容诊断", False) == "diagnosis"
    assert deliverable_kind_for("operation.analytics.review", "运营复盘", False) == "retrospective"
```

- [ ] **Step 2: 写 V2 判别联合和未知字段失败关闭测试**

```python
import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.deliverables import DeliverableSetV2


def test_ranked_digest_v2_requires_typed_items_and_rejects_unknown_fields() -> None:
    payload = ranked_digest_payload()
    parsed = DeliverableSetV2.model_validate(payload)
    assert parsed.deliverables[0].content.kind == "ranked_digest"
    payload["deliverables"][0]["content"]["unexpected"] = True
    with pytest.raises(ValidationError):
        DeliverableSetV2.model_validate(payload)
```

测试 fixture 必须在同一文件内返回完整 V2 JSON，至少包含 `summary`、一个 `RankedItemV2`、一个 `CitationV2`、`provenance`、空 `next_actions` 和空 `warnings`，不得依赖真实网络。

- [ ] **Step 3: 运行测试并确认红灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/contracts/test_deliverable_v2_contracts.py tests/unit/agents/operation/test_delivery_kind.py -q
```

Expected: collection FAIL，原因是 `DeliverableSetV2` 与 `delivery_kind_for` 尚不存在。

- [ ] **Step 4: 实现交付类型映射**

```python
from typing import Literal

DeliverableKindV2 = Literal[
    "ranked_digest",
    "platform_content",
    "action_plan",
    "diagnosis",
    "retrospective",
]

_KIND_BY_CAPABILITY: dict[str, DeliverableKindV2] = {
    "operation.research.insight": "ranked_digest",
    "operation.content.create": "platform_content",
    "operation.channel.content": "platform_content",
    "operation.brand.strategy": "action_plan",
    "operation.ip.strategy": "action_plan",
    "operation.product.plan": "action_plan",
    "operation.campaign.plan": "action_plan",
    "operation.user_growth.plan": "action_plan",
    "operation.community.plan": "action_plan",
    "operation.quality.review": "diagnosis",
    "operation.analytics.review": "retrospective",
}


def deliverable_kind_for(
    capability_id: str, platform: str, research: bool
) -> DeliverableKindV2:
    if research and platform == "research":
        return "ranked_digest"
    try:
        return _KIND_BY_CAPABILITY[capability_id]
    except KeyError as exc:
        raise ValueError("DELIVERABLE_KIND_UNSUPPORTED") from exc
```

- [ ] **Step 5: 在 `contracts/deliverables.py` 增加完整 V2 模型**

使用 `ConfigDict(extra="forbid", frozen=True)`。内容联合使用 `Field(discriminator="kind")`，交付物顶层联合使用 `Field(discriminator="deliverable_kind")`。必须定义并导出以下具体模型，不得用 `dict[str, object]` 替代：

```python
ConfidenceV2 = Literal["high", "medium", "low"]
VerificationStatusV2 = Literal["verified", "partially_verified", "unverified", "conflicted"]

class CitationV2(BaseModel):
    citation_id: str
    url: str
    title: str | None = None
    source: str | None = None
    published_at: str | None = None
    source_type: Literal["api", "rss", "public_page", "official", "community"]
    source_tier: Literal["primary", "secondary", "community"]
    verification_status: VerificationStatusV2
    supports_item_ids: list[str] = Field(default_factory=list, max_length=100)
    independent_source_group: str | None = None

class RankedItemV2(BaseModel):
    item_id: str
    rank: int = Field(ge=1, le=100)
    title: str = Field(min_length=1, max_length=500)
    occurred_at: str | None = None
    summary: str = Field(min_length=1, max_length=2_000)
    why_it_matters: str = Field(min_length=1, max_length=1_000)
    content_angles: list[str] = Field(default_factory=list, max_length=10)
    metrics: list[str] = Field(default_factory=list, max_length=20)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    confidence: ConfidenceV2
    verification_status: VerificationStatusV2

class RankedDigestContentV2(BaseModel):
    kind: Literal["ranked_digest"] = "ranked_digest"
    selection_summary: str = Field(min_length=1, max_length=2_000)
    ranking_basis: Literal["importance", "recency", "heat", "mixed"]
    items: list[RankedItemV2] = Field(min_length=1, max_length=100)

class PlatformContentV2(BaseModel):
    kind: Literal["platform_content"] = "platform_content"
    body_markdown: str = Field(min_length=1, max_length=100_000)
    hashtags: list[str] = Field(default_factory=list, max_length=100)
    format_notes: list[str] = Field(default_factory=list, max_length=50)

class ActionPhaseV2(BaseModel):
    phase_id: str
    title: str
    actions: list[str] = Field(min_length=1, max_length=50)
    metrics: list[str] = Field(default_factory=list, max_length=20)

class ActionPlanContentV2(BaseModel):
    kind: Literal["action_plan"] = "action_plan"
    goal: str
    audience: str
    phases: list[ActionPhaseV2] = Field(min_length=1, max_length=20)
    metrics: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=50)

class FindingV2(BaseModel):
    finding_id: str
    title: str
    evidence: list[str] = Field(default_factory=list, max_length=50)
    priority: Literal["high", "medium", "low"]
    recommendation: str

class DiagnosisContentV2(BaseModel):
    kind: Literal["diagnosis"] = "diagnosis"
    findings: list[FindingV2] = Field(min_length=1, max_length=50)
    data_gaps: list[str] = Field(default_factory=list, max_length=50)

class RetrospectiveContentV2(BaseModel):
    kind: Literal["retrospective"] = "retrospective"
    objectives: list[str] = Field(min_length=1, max_length=50)
    outcomes: list[str] = Field(default_factory=list, max_length=50)
    gaps: list[str] = Field(default_factory=list, max_length=50)
    causes: list[str] = Field(default_factory=list, max_length=50)
    next_steps: list[str] = Field(min_length=1, max_length=50)
```

用以下顶层结构定义五个具体交付模型。每个子类同时固定 `deliverable_kind` 和对应 `content` 类型，避免根据嵌套字段或正文猜交付类型：

```python
from typing import Annotated, Literal


class WarningV2(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1_000)


class OperationDeliverableBaseV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["deliverable/2"] = "deliverable/2"
    deliverable_id: str = Field(min_length=1, max_length=100)
    platform: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    lead: str = Field(min_length=1, max_length=2_000)
    citations: list[CitationV2] = Field(default_factory=list, max_length=100)
    copy_text: str = Field(min_length=1, max_length=100_000)
    warnings: list[WarningV2] = Field(default_factory=list, max_length=100)


class RankedDigestDeliverableV2(OperationDeliverableBaseV2):
    deliverable_kind: Literal["ranked_digest"] = "ranked_digest"
    content: RankedDigestContentV2


class PlatformContentDeliverableV2(OperationDeliverableBaseV2):
    deliverable_kind: Literal["platform_content"] = "platform_content"
    content: PlatformContentV2


class ActionPlanDeliverableV2(OperationDeliverableBaseV2):
    deliverable_kind: Literal["action_plan"] = "action_plan"
    content: ActionPlanContentV2


class DiagnosisDeliverableV2(OperationDeliverableBaseV2):
    deliverable_kind: Literal["diagnosis"] = "diagnosis"
    content: DiagnosisContentV2


class RetrospectiveDeliverableV2(OperationDeliverableBaseV2):
    deliverable_kind: Literal["retrospective"] = "retrospective"
    content: RetrospectiveContentV2


OperationDeliverableV2 = Annotated[
    RankedDigestDeliverableV2
    | PlatformContentDeliverableV2
    | ActionPlanDeliverableV2
    | DiagnosisDeliverableV2
    | RetrospectiveDeliverableV2,
    Field(discriminator="deliverable_kind"),
]
```

同一文件继续定义并导出：

- `DeliverySummaryV2`: `message`、`result_count >= 0`、`complete`；
- `DeliveryProvenanceV2`: `source_count >= 0`、`verified_source_count >= 0`、`candidate_count >= 0`、`merged_event_count >= 0`、`retained_count >= 0`、`eliminated_count >= 0`；`collection_window_start/end` 均为可空的 UTC aware `datetime`，必须同时为空或同时存在且 start < end；`ranking_basis` 为可空的 `Literal["importance", "recency", "heat", "mixed"]`；并校验 `verified_source_count <= source_count`；
- `NextActionV2`: `action_id: str`、`action_type: Literal["rewrite_for_platform", "expand_item", "generate_script", "replace_candidates", "show_sources", "refine_constraints"]`、`label: str`、`target_deliverable_id: str | None`、`target_item_ids: list[str]`、`intent_patch: dict[str, JsonValue] = Field(default_factory=dict, max_length=50)`、`requires_user_input: bool`；`JsonValue` 复用 `contracts.stream_events` 的严格 JSON 类型，不允许任意 Python 对象；
- `DeliverableSetV2`: 固定 `contract_version="deliverable-set/2"`，并包含 `run_id`、`intent_revision >= 0`、`summary`、最多 20 个 `deliverables`、最多 20 个 `next_actions`、可空 `provenance`、`degraded`、最多 100 个 `warnings`；
- `DeliverableSet = Annotated[DeliverableSetV1 | DeliverableSetV2, Field(discriminator="contract_version")]`，只能由 `contract_version` 分派。

- [ ] **Step 6: 运行目标测试并确认绿灯**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/contracts/test_deliverable_v2_contracts.py tests/unit/agents/operation/test_delivery_kind.py -q
```

Expected: PASS；同时确认既有 `tests/contracts/test_stream_event_contracts.py` 仍通过。

- [ ] **Step 7: 更新进度账本并保存文件快照清单**

创建进度账本，记录 Task 1 的红灯命令、绿灯命令、修改文件和 `DeliverableSetV1` 未变的检查结果。后续任务只追加记录，不覆盖历史；不得创建 Git 提交。
