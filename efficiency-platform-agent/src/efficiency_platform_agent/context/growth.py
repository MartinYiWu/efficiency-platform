"""同已发布窗口的实际/预测压力；不调用模型，不把预测记作usage。"""

from dataclasses import dataclass
from typing import Literal

from efficiency_platform_agent.core.context_control import (
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import require_count, require_id

Pressure = Literal["NORMAL", "PREPARE", "INTERVENE", "OVERFLOW"]


@dataclass(frozen=True, slots=True)
class GrowthBound:
    """由已发布工具/专家投影合同给出的可见输入增长上界。"""

    upper_bound: int
    source_ref: str
    version: str

    def __post_init__(self) -> None:
        require_count(self.upper_bound)
        require_id(self.source_ref)
        require_id(self.version)


@dataclass(frozen=True, slots=True)
class GrowthDecision:
    H_ctx: int
    T: int
    G: int | None
    actual_pressure: Pressure
    predicted_pressure: Pressure | Literal["UNKNOWN", "MATERIALIZED"]
    predicted_total: int | None
    growth_source_ref: str | None
    growth_version: str | None
    measurement_method: str


def _pressure(cap: int, total: int) -> Pressure:
    if cap <= 0 or total > cap:
        return "OVERFLOW"
    if total * 100 <= cap * 70:
        return "NORMAL"
    if total * 100 <= cap * 85:
        return "PREPARE"
    return "INTERVENE"


def evaluate_growth(
    limits: WindowLimits,
    measurement: TokenMeasurement,
    *,
    generation_bound: GrowthBound | None = None,
    materialized: TokenMeasurement | None = None,
) -> GrowthDecision:
    """measurement必须是完整请求；物化后传新完整测量，不再叠加原预测G。"""

    if type(limits) is not WindowLimits or any(
        type(item) is not TokenMeasurement or not item.verified
        for item in (measurement, *(() if materialized is None else (materialized,)))
    ):
        raise ValueError("CONTEXT_CAPACITY_UNVERIFIED")
    if generation_bound is not None and type(generation_bound) is not GrowthBound:
        raise ValueError("CONTEXT_GROWTH_BOUND_INVALID")
    if materialized is not None and materialized.method != measurement.method:
        raise ValueError("CONTEXT_MEASUREMENT_METHOD_MISMATCH")
    current = measurement if materialized is None else materialized
    cap, total = limits.input_cap(), current.total_upper_bound
    growth = generation_bound.upper_bound if generation_bound is not None else None
    predicted_total = (
        total + growth if growth is not None and materialized is None else None
    )
    predicted: Pressure | Literal["UNKNOWN", "MATERIALIZED"] = (
        "MATERIALIZED" if materialized is not None else "UNKNOWN"
    )
    if predicted_total is not None:
        predicted = _pressure(cap, predicted_total)
    return GrowthDecision(
        cap,
        total,
        growth,
        _pressure(cap, total),
        predicted,
        predicted_total,
        generation_bound.source_ref if generation_bound is not None else None,
        generation_bound.version if generation_bound is not None else None,
        current.method,
    )
