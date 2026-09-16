"""多 Agent 执行入口，复用 S2 GraphRuntime。"""

from __future__ import annotations

from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.routing.strategy_router import StrategySelection


class OperationSupervisorExecutor:
    """接收已路由选择并委托唯一 S2 运行时。"""

    def __init__(self, graph_runtime) -> None:
        self.graph_runtime = graph_runtime

    async def execute(self, initial_state: dict[str, object], selection=None):
        """不重新路由，直接调用 S2 GraphRuntime.execute。"""

        selection = selection or StrategySelection(
            StrategyMode.MULTI_AGENT, "s4:operation-supervisor", "MULTI_AGENT"
        )
        if selection.mode is not StrategyMode.MULTI_AGENT:
            raise ValueError("策略选择必须是MULTI_AGENT")
        return await self.graph_runtime.execute(selection, initial_state)

    async def resume(
        self,
        selection,
        run_id: str,
        checkpoint_id: str,
        resume_value,
        *,
        tenant_id: str = "",
    ):
        """通过 S2 resume 入口恢复执行。"""

        return await self.graph_runtime.resume(
            selection,
            run_id,
            checkpoint_id,
            resume_value,
            tenant_id=tenant_id,
        )


__all__ = ["OperationSupervisorExecutor"]
