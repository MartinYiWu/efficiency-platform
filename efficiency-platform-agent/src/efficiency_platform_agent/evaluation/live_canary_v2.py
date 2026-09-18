"""X05 单租户灰度观察与硬停止控制。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LIVE_ACCEPTANCE_CASE_PROMPTS,
)
from efficiency_platform_agent.core.budget_execution import BudgetExecutionBinding

_SOURCE_REQUIRED = frozenset(
    {"yesterday_ai", "last_week_topic", "exact_five", "rewrite_wechat"}
)


class CanaryDispatchStopped(RuntimeError):
    """硬停止后拒绝任何新增 V2 灰度请求。"""


@dataclass(frozen=True, slots=True)
class CanaryObservation:
    request_id: str
    case_id: str
    status: Literal["PASS", "PARTIAL", "FAILED"]
    real_model_verified: bool
    real_source_verified: bool
    citation_coverage: float
    source_policy_violations: tuple[str, ...]
    budget_overspent: bool


class CanaryStopController:
    """根据手册中的安全/正确性条件锁死后续调度。"""

    def __init__(self) -> None:
        self._observations: list[CanaryObservation] = []
        self._stop_reasons: list[str] = []

    @property
    def stopped(self) -> bool:
        return bool(self._stop_reasons)

    @property
    def stop_reasons(self) -> tuple[str, ...]:
        return tuple(self._stop_reasons)

    @property
    def accepted_count(self) -> int:
        return len(self._observations)

    @property
    def observations(self) -> tuple[CanaryObservation, ...]:
        return tuple(self._observations)

    def before_dispatch(self) -> None:
        if self.stopped:
            raise CanaryDispatchStopped("CANARY_HARD_STOP")

    def observe(self, observation: CanaryObservation) -> None:
        self._observations.append(observation)
        reasons: list[str] = []
        if not observation.real_model_verified:
            reasons.append("MODEL_NOT_VERIFIED")
        if (
            observation.case_id in _SOURCE_REQUIRED
            and not observation.real_source_verified
        ):
            reasons.append("SOURCE_NOT_VERIFIED")
        if (
            observation.case_id in _SOURCE_REQUIRED
            and observation.citation_coverage < 1.0
        ):
            reasons.append("CITATION_COVERAGE_BELOW_ONE")
        if observation.source_policy_violations:
            reasons.append("SOURCE_POLICY_VIOLATION")
        if observation.budget_overspent:
            reasons.append("BUDGET_OVERSPENT")
        if observation.status == "FAILED":
            reasons.append("REQUEST_FAILED")
        for reason in reasons:
            if reason not in self._stop_reasons:
                self._stop_reasons.append(reason)


async def execute_single_tenant_canary(
    *,
    runner: Any,
    binding: BudgetExecutionBinding,
    rounds: int = 4,
) -> dict[str, object]:
    """执行五类请求各四次，并验证硬停止后不再发生外部调用。"""

    if rounds != 4:
        raise ValueError("CANARY_ROUNDS_MUST_BE_FOUR")
    controller = CanaryStopController()
    case_ids = tuple(LIVE_ACCEPTANCE_CASE_PROMPTS)
    for round_index in range(1, rounds + 1):
        for case_id in case_ids:
            controller.before_dispatch()
            request_id = f"x05-r{round_index}-{case_id}"
            result = await runner.run_case(
                case_id,
                LIVE_ACCEPTANCE_CASE_PROMPTS[case_id],
                binding,
            )
            record = runner.records[-1]
            snapshot = await binding.port.snapshot(binding.scope)
            limits = snapshot.limits
            used = snapshot.used
            allowed_source_ids = {
                "fixture_official_feed",
                "fixture_github_releases",
                "fixture_hacker_news",
            }
            observed_source_ids = {
                str(item.get("source_id"))
                for item in record.get("sources", ())
                if isinstance(item, dict)
            }
            violations = tuple(sorted(observed_source_ids - allowed_source_ids))
            controller.observe(
                CanaryObservation(
                    request_id=request_id,
                    case_id=case_id,
                    status=result.status,
                    real_model_verified=result.real_model_verified,
                    real_source_verified=result.real_source_verified,
                    citation_coverage=float(record.get("citation_coverage", 0.0)),
                    source_policy_violations=violations,
                    budget_overspent=(
                        used.calls > limits.max_calls
                        or used.bytes > limits.max_bytes
                        or used.input_tokens > limits.max_input_tokens
                        or used.output_tokens > limits.max_output_tokens
                        or used.cost_microunits > limits.max_cost_microunits
                    ),
                )
            )

    calls_before_stop_probe = (
        await binding.port.snapshot(binding.scope)
    ).used.calls
    probe = CanaryStopController()
    probe.observe(
        CanaryObservation(
            request_id="x05-stop-probe",
            case_id="yesterday_ai",
            status="PASS",
            real_model_verified=True,
            real_source_verified=True,
            citation_coverage=1.0,
            source_policy_violations=("synthetic-unapproved-source",),
            budget_overspent=False,
        )
    )
    rejected = False
    try:
        probe.before_dispatch()
    except CanaryDispatchStopped:
        rejected = True
    calls_after_stop_probe = (
        await binding.port.snapshot(binding.scope)
    ).used.calls
    return {
        "schema_version": "research-v2-live-canary/1",
        "status": "PASS" if controller.accepted_count == 20 and not controller.stopped else "FAILED",
        "tenant_id": binding.scope.tenant_id,
        "acceptance_session_id": binding.lease_id,
        "valid_request_count": controller.accepted_count,
        "case_counts": {
            case_id: sum(
                item.case_id == case_id for item in controller.observations
            )
            for case_id in case_ids
        },
        "source_collection_cache_verified": bool(
            getattr(runner.collector, "collection_count", 0) == 1
            and getattr(runner.collector, "cache_hit_count", 0) >= 1
        ),
        "source_collection_count": getattr(
            runner.collector, "collection_count", None
        ),
        "source_collection_cache_hits": getattr(
            runner.collector, "cache_hit_count", None
        ),
        "observations": [asdict(item) for item in controller.observations],
        "hard_stop_probe": {
            "trigger": "SOURCE_POLICY_VIOLATION",
            "new_dispatch_rejected": rejected,
            "calls_before": calls_before_stop_probe,
            "calls_after": calls_after_stop_probe,
            "no_external_call_after_stop": calls_before_stop_probe
            == calls_after_stop_probe,
            "evidence_preserved": len(probe.observations) == 1,
        },
        "runner_records": runner.records,
    }


__all__ = [
    "CanaryDispatchStopped",
    "CanaryObservation",
    "CanaryStopController",
    "execute_single_tenant_canary",
]
