"""显式图注册表，不进行隐式策略到运行时的分派。"""

from __future__ import annotations

import json

from efficiency_platform_agent.core.enums import StrategyMode
from efficiency_platform_agent.core.run import JsonObject, JsonValue

from .contracts import GraphRegistration


def validate_strategy_payload(
    schema_version: str, payload: JsonObject, allowed_keys: frozenset[str]
) -> None:
    """校验版本化 payload 的大小、深度、成员数与顶层键白名单。"""
    if not isinstance(payload, JsonObject) or not isinstance(schema_version, str):
        raise TypeError("策略 payload 无效")
    if not schema_version.strip() or not isinstance(allowed_keys, frozenset):
        raise ValueError("策略 payload 版本或白名单无效")
    if any(not isinstance(key, str) or len(key) > 128 for key, _ in payload.items):
        raise ValueError("策略 payload 键无效")
    if any(key not in allowed_keys for key, _ in payload.items):
        raise ValueError("策略 payload 存在未声明字段")

    def walk(value: JsonValue, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("策略 payload 嵌套过深")
        if isinstance(value, JsonObject):
            if len(value.items) > 128:
                raise ValueError("策略 payload 成员过多")
            for key, child in value.items:
                if len(key) > 128:
                    raise ValueError("策略 payload 键过长")
                walk(child, depth + 1)
            return
        if isinstance(value, tuple):
            if len(value) > 128:
                raise ValueError("策略 payload 成员过多")
            for child in value:
                walk(child, depth + 1)
            return

    walk(payload)

    def plain(value: JsonValue) -> object:
        if isinstance(value, JsonObject):
            return {key: plain(child) for key, child in value.items}
        if isinstance(value, tuple):
            return [plain(child) for child in value]
        return value

    if (
        len(
            json.dumps(
                plain(payload), ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        )
        > 65536
    ):
        raise ValueError("策略 payload 超过大小限制")


class GraphRegistry:
    def __init__(self) -> None:
        self._by_mode: dict[StrategyMode, GraphRegistration] = {}
        self._by_id: dict[str, GraphRegistration] = {}

    def register(self, registration: GraphRegistration) -> None:
        if not isinstance(registration, GraphRegistration):
            raise TypeError("registration must be GraphRegistration")
        if registration.strategy in self._by_mode:
            raise ValueError("strategy mode already registered")
        if registration.graph_id in self._by_id:
            raise ValueError("graph id already registered")
        self._by_mode[registration.strategy] = registration
        self._by_id[registration.graph_id] = registration

    def get(self, strategy: StrategyMode):
        if not isinstance(strategy, StrategyMode):
            raise TypeError("strategy must be StrategyMode")
        try:
            return self._by_mode[strategy]
        except KeyError as exc:
            raise KeyError(strategy) from exc

    def available_modes(self) -> frozenset[StrategyMode]:
        return frozenset(self._by_mode)


class _EmptyPayloadAdapter:
    def adapt(self, schema_version: str, payload: JsonObject):
        validate_strategy_payload(schema_version, payload, frozenset())
        return payload


def build_default_registry(
    *,
    model_runtime=None,
    context_builder=None,
    tool_runtime=None,
    checkpointer=None,
    allow_waiting_input: bool = False,
) -> GraphRegistry:
    """创建只包含 Direct/Workflow 的默认注册表。"""
    from efficiency_platform_agent.core.enums import RunStatus

    from .builders.direct import DirectGraphBuilder
    from .builders.workflow import WorkflowGraphBuilder

    registry = GraphRegistry()
    statuses_set = {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }
    if allow_waiting_input:
        statuses_set.add(RunStatus.WAITING_INPUT)
    statuses = frozenset(statuses_set)
    registry.register(
        GraphRegistration(
            "direct",
            StrategyMode.DIRECT,
            "1.0.0",
            "s2:direct:1",
            "strategy.none/1",
            frozenset(),
            statuses,
            DirectGraphBuilder(
                model_runtime=model_runtime,
                context_builder=context_builder,
                tool_runtime=tool_runtime,
                checkpointer=checkpointer,
            ),
            _EmptyPayloadAdapter(),
        )
    )
    registry.register(
        GraphRegistration(
            "workflow",
            StrategyMode.WORKFLOW,
            "1.0.0",
            "s2:workflow:1",
            "strategy.none/1",
            frozenset(),
            statuses,
            WorkflowGraphBuilder(
                model_runtime=model_runtime,
                context_builder=context_builder,
                tool_runtime=tool_runtime,
                checkpointer=checkpointer,
            ),
            _EmptyPayloadAdapter(),
        )
    )
    return registry
