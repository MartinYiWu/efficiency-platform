"""模型池公共导出；实际策略由既有 ModelPolicyRouter 负责。"""

from dataclasses import dataclass
from typing import Any

from ..core.model import (
    ModelCandidate,
    ModelDemand,
    ModelExecutionResult,
    ModelSelection,
)


@dataclass(frozen=True, slots=True)
class ModelSelectionInput:
    """旧意图适配层的选择输入，策略仍完全由 ModelPolicyRouter 执行。"""

    tier: str = "balanced"


@dataclass(frozen=True, slots=True)
class SelectedModel:
    """旧适配层需要的模型名称视图。"""

    model: str
    degraded: bool = False
    degraded_from: str | None = None


class ModelSelector:
    """旧意图端口的兼容薄适配；真实运行时使用 ModelRuntime 路由。"""

    def __init__(
        self, candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...]
    ) -> None:
        from ..core.model import ModelTier

        tier_map = {
            "fast": ModelTier.FAST,
            "balanced": ModelTier.BALANCED,
            "strong": ModelTier.STRONG,
        }
        converted = []
        for index, candidate in enumerate(candidates):
            tier = tier_map.get(
                str(candidate.get("tier", "balanced")), ModelTier.BALANCED
            )
            converted.append(
                ModelCandidate(
                    str(candidate.get("model", f"candidate-{index}")),
                    str(candidate.get("provider_id", "deepseek_direct")),
                    str(candidate.get("model", f"candidate-{index}")),
                    tier,
                    True,
                    True,
                    128_000,
                    bool(candidate.get("enabled", True)),
                    False,
                )
            )
        self._candidates = tuple(converted)

    def select(self, task: ModelSelectionInput) -> SelectedModel:
        from ..core.model import ModelTier

        tier = ModelTier(task.tier)
        order = {
            ModelTier.STRONG: (ModelTier.STRONG, ModelTier.BALANCED, ModelTier.FAST),
            ModelTier.BALANCED: (ModelTier.BALANCED, ModelTier.FAST),
            ModelTier.FAST: (ModelTier.FAST,),
        }[tier]
        candidates = tuple(
            candidate
            for candidate_tier in order
            for candidate in self._candidates
            if candidate.tier is candidate_tier and candidate.enabled
        )
        if not candidates:
            raise RuntimeError("MODEL_UNAVAILABLE")
        selected = candidates[0]
        return SelectedModel(
            selected.logical_model,
            selected.tier is not tier,
            task.tier if selected.tier is not tier else None,
        )


__all__ = [
    "ModelCandidate",
    "ModelDemand",
    "ModelExecutionResult",
    "ModelSelection",
    "ModelSelectionInput",
    "ModelSelector",
    "SelectedModel",
]
