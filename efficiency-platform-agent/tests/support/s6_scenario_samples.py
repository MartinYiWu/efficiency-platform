"""S6 仅测试使用的 24 个固定样本和生产提交转换器。"""

from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.agents.operation.contracts import (
    EvidencePack,
    OperationRequest,
    OperationTaskSpec,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioSubmission,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from tests.support.s2_operation_fakes import (
    FakeS2OperationIntentPort,
    build_empty_evidence_pack,
    build_operation_request,
)


@dataclass(frozen=True, slots=True)
class ScenarioSample:
    """包含测试期望值的样本；该类型不得进入生产源码。"""

    sample_id: str
    contract_version: str
    submission_id: str
    scenario_id: str
    manifest_semantic_version: str
    plan_id: str
    request: OperationRequest
    task_spec: OperationTaskSpec
    profile_candidates: tuple[object, ...]
    evidence_pack: EvidencePack | None
    expected_completion_status: CompletionStatus
    expected_deliverable_ids: tuple[str, ...]
    expected_warning_codes: frozenset[str]


_PACK_STATES = (
    ("industry_digest", "waiting-time-window", "research-insufficient"),
    ("multi_platform_content", "waiting-platforms", "toutiao-failed"),
    ("brand_operation_plan", "waiting-brand-goal", "research-unavailable"),
    ("ip_operation_plan", "waiting-ip-audience", "channel-unavailable"),
    ("campaign_plan", "waiting-campaign-window", "growth-partial"),
    ("content_calendar", "waiting-calendar-range", "profile-missing"),
    ("growth_experiment", "waiting-funnel", "analytics-unavailable"),
    ("operation_review", "waiting-metric-definition", "data-unreadable"),
)


def _sample(pack: str, state: str, suffix: str) -> ScenarioSample:
    request = build_operation_request(tenant_id="tenant-s6", user_id="user-s6")
    task = FakeS2OperationIntentPort().normalize(request)
    sample_id = f"{pack}.{suffix}/1"
    status = {
        "complete": CompletionStatus.COMPLETE,
        "waiting_input": CompletionStatus.WAITING_INPUT,
        "partial": CompletionStatus.PARTIAL,
    }[state]
    return ScenarioSample(
        sample_id,
        "scenario-submission/1",
        f"submission-{pack}-{suffix}",
        pack,
        "1.0.0",
        f"plan-{pack}-{suffix}",
        request,
        task,
        (),
        build_empty_evidence_pack(task.task_id),
        status,
        (),
        frozenset(),
    )


def build_s6_samples() -> tuple[ScenarioSample, ...]:
    """构造八个场景各完整、等待、部分三类固定样本。"""

    samples: list[ScenarioSample] = []
    for pack, waiting_suffix, partial_suffix in _PACK_STATES:
        samples.extend(
            (
                _sample(pack, "complete", "complete"),
                _sample(pack, "waiting_input", waiting_suffix),
                _sample(pack, "partial", partial_suffix),
            )
        )
    return tuple(samples)


def submission_from_sample(sample: ScenarioSample) -> ScenarioSubmission:
    """逐字段复制生产入站字段，显式丢弃 sample 与 expected 字段。"""

    if not isinstance(sample, ScenarioSample):
        raise TypeError("sample必须是ScenarioSample")
    return ScenarioSubmission(
        contract_version=sample.contract_version,
        submission_id=sample.submission_id,
        scenario_id=sample.scenario_id,
        manifest_semantic_version=sample.manifest_semantic_version,
        plan_id=sample.plan_id,
        request=sample.request,
        task_spec=sample.task_spec,
        profile_candidates=sample.profile_candidates,
        evidence_pack=sample.evidence_pack,
    )


def sample_by_id(sample_id: str) -> ScenarioSample:
    """按完整样本 ID 精确查找，不支持模糊版本。"""

    for sample in build_s6_samples():
        if sample.sample_id == sample_id:
            return sample
    raise KeyError(sample_id)


__all__ = [
    "ScenarioSample",
    "build_s6_samples",
    "sample_by_id",
    "submission_from_sample",
]
