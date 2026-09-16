"""S4 组合根：向既有 GraphRegistry 注册 MULTI_AGENT 图。"""

from __future__ import annotations

from efficiency_platform_agent.contracts.operation_resume import (
    OperationResumeValidator,
)
from efficiency_platform_agent.contracts.operation_strategy import (
    OperationStrategyPayloadAdapter,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.orchestration.builders.operation_supervisor import (
    OperationSupervisorGraphBuilder,
)
from efficiency_platform_agent.orchestration.contracts import GraphRegistration
from efficiency_platform_agent.strategies.multi_agent.nodes import (
    SupervisorDependencies,
)


def register_operation_supervisor(
    registry, dependencies: SupervisorDependencies, limits=None
):
    """在现有注册表追加唯一 MULTI_AGENT registration。"""

    adapter = OperationStrategyPayloadAdapter()
    registration = GraphRegistration(
        graph_id="operation-supervisor",
        strategy=StrategyMode.MULTI_AGENT,
        graph_version="1.0.0",
        checkpoint_ns="s2:multi_agent:1",
        strategy_payload_schema_version=adapter.schema_version,
        allowed_strategy_payload_keys=adapter.allowed_keys,
        allowed_next_statuses=frozenset(
            {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.WAITING_INPUT,
            }
        ),
        builder=OperationSupervisorGraphBuilder(dependencies, limits),
        payload_adapter=adapter,
        resume_validator=OperationResumeValidator(),
    )
    registry.register(registration)
    return registration


__all__ = ["register_operation_supervisor"]
