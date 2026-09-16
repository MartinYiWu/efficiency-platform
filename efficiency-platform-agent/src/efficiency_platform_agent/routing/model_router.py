"""基于能力、预算与健康状态的确定性模型候选路由。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ..core.budget import RemainingBudget
from ..core.model import ModelCandidate, ModelCandidateSelector, ModelDemand, ModelTier

_DOWNGRADE_ORDER: dict[ModelTier, tuple[ModelTier, ...]] = {
    ModelTier.STRONG: (ModelTier.STRONG, ModelTier.BALANCED, ModelTier.FAST),
    ModelTier.BALANCED: (ModelTier.BALANCED, ModelTier.FAST),
    ModelTier.FAST: (ModelTier.FAST,),
}


def synthetic_model_candidates() -> tuple[ModelCandidate, ...]:
    """返回 S2 唯一允许的三个合成候选，不包含 Secret。"""
    return (
        ModelCandidate(
            "fake_fast",
            "fake_fast",
            "fake_fast",
            ModelTier.FAST,
            True,
            True,
            16_384,
            True,
            True,
        ),
        ModelCandidate(
            "fake_balanced",
            "fake_balanced",
            "fake_balanced",
            ModelTier.BALANCED,
            True,
            True,
            32_768,
            True,
            True,
        ),
        ModelCandidate(
            "fake_strong",
            "fake_strong",
            "fake_strong",
            ModelTier.STRONG,
            True,
            True,
            64_000,
            True,
            True,
        ),
    )


class ModelPolicyRouter(ModelCandidateSelector):
    """按请求层级向下排序并过滤不满足硬约束的候选。"""

    def __init__(
        self,
        candidates: Iterable[ModelCandidate] | None = None,
        *,
        unavailable_candidate_ids: frozenset[str] = frozenset(),
    ) -> None:
        self._candidates = tuple(
            synthetic_model_candidates() if candidates is None else candidates
        )
        if any(
            not isinstance(candidate, ModelCandidate) for candidate in self._candidates
        ):
            raise TypeError("candidates 只能包含 ModelCandidate")
        self._unavailable = frozenset(unavailable_candidate_ids)

    def candidates(
        self,
        demand: ModelDemand,
        *,
        remaining_budget: RemainingBudget,
        unavailable_candidate_ids: frozenset[str],
    ) -> Sequence[ModelCandidate]:
        """返回稳定、有限且满足硬能力与预算的候选序列。"""
        if not isinstance(demand, ModelDemand):
            raise TypeError("demand 必须是 ModelDemand")
        blocked = self._unavailable | frozenset(unavailable_candidate_ids)
        by_tier: dict[ModelTier, list[ModelCandidate]] = {
            tier: [] for tier in ModelTier
        }
        for candidate in self._candidates:
            if not candidate.enabled or candidate.candidate_id in blocked:
                continue
            if (
                demand.requires_structured_output
                and not candidate.supports_structured_output
            ):
                continue
            if demand.requires_tools and not candidate.supports_tools:
                continue
            if (
                candidate.max_context_tokens
                < demand.estimated_input_tokens + demand.max_output_tokens
            ):
                continue
            if (
                remaining_budget.iterations <= 0
                or remaining_budget.input_tokens < demand.estimated_input_tokens
            ):
                continue
            if remaining_budget.output_tokens < demand.max_output_tokens:
                continue
            if remaining_budget.timeout_ms <= 0:
                continue
            by_tier[candidate.tier].append(candidate)
        ordered: list[ModelCandidate] = []
        for tier in _DOWNGRADE_ORDER[demand.requested_tier]:
            ordered.extend(sorted(by_tier[tier], key=lambda item: item.candidate_id))
        return tuple(ordered)
