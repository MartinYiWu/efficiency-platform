"""分析复盘 Specialist，原始行仅在受控 lease 内短暂存在。"""

from __future__ import annotations

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.specialists._base import (
    OperationSpecialistBase,
)
from efficiency_platform_agent.capabilities.analytics.contracts import (
    AnalyticsDataset,
    AnalyticsFileReadRequest,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import JsonObject, RunResult, SupervisorTask


class AnalyticsReviewAgent(OperationSpecialistBase):
    """确定性复核摘要并生成趋势、异常和假设，不执行外部动作。"""

    def __init__(self, reader=None) -> None:
        super().__init__(
            agent_id="operation.analytics.review",
            capability_id=OperationSpecialistCapabilityId.ANALYTICS_REVIEW.value,
            task_type="operation.analytics_review",
            prompt_bundle_id="operation.analytics.review/1",
            quality_policy_id="operation-analytics-quality/1",
            output_title="运营数据复盘",
            output_label="analytics_review",
            max_input_tokens=5_000,
            max_output_tokens=3_000,
        )
        self.reader = reader

    async def summarize(self, request: AnalyticsFileReadRequest) -> dict[str, object]:
        """在 lease 内聚合数据，离开 lease 后仅返回标量摘要。"""

        if self.reader is None:
            raise ValueError("ANALYTICS_READER_UNAVAILABLE")
        async with self.reader.open(request) as dataset:
            if not isinstance(dataset, AnalyticsDataset):
                raise ValueError("ANALYTICS_DATASET_INVALID")  # noqa: TRY004
            totals: dict[str, int] = {}
            for row in dataset.rows:
                for index, column in enumerate(dataset.columns):
                    value = row[index]
                    if isinstance(value, int) and not isinstance(value, bool):
                        totals[column.name] = totals.get(column.name, 0) + value
            # 离开上下文后返回的只有有界标量，不携带 rows。
            return {
                "dataset_id": request.dataset_reference.dataset_id,
                "totals": totals,
                "causality": "hypothesis",
            }

    async def run(self, task: SupervisorTask) -> RunResult:
        """在无模型依赖的离线路径执行摘要复核；缺少请求时沿用公共适配器。"""

        raw = dict(task.input_data.items)
        request = raw.get("analytics_request")
        if not isinstance(request, AnalyticsFileReadRequest):
            return await super().run(task)
        try:
            summary = await self.summarize(request)
            output = JsonObject(
                (
                    ("content", "analytics_review"),
                    ("dataset_id", summary["dataset_id"]),
                    ("totals", JsonObject(tuple(summary["totals"].items()))),
                    ("causality", "hypothesis"),
                )
            )
            return RunResult(
                task.parent_run_id,
                RunStatus.SUCCEEDED,
                StrategyMode.MULTI_AGENT,
                output,
            )
        except Exception:  # noqa: BLE001
            return RunResult(
                task.parent_run_id,
                RunStatus.FAILED,
                StrategyMode.MULTI_AGENT,
                JsonObject((("content", "ANALYTICS_MODEL_FAILED"),)),
            )


__all__ = ["AnalyticsReviewAgent"]
