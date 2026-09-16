from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from efficiency_platform_agent.core.agent import AgentSpec, CapabilityRequirement
from efficiency_platform_agent.core.enums import AgentKind
from efficiency_platform_agent.core.ports import AgentPlugin

from .errors import AgentNotFoundError, AgentRegistrationConflictError
from .validation import AgentValidator

type AgentBuilder = Callable[[], AgentPlugin]


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    """一个已经通过定义校验的显式 Agent 注册项。"""

    spec: AgentSpec
    builder: AgentBuilder


class AgentRegistry:
    """提供确定性 Agent 注册、查找和能力匹配。"""

    def __init__(self, validator: AgentValidator | None = None) -> None:
        self._validator = validator or AgentValidator()
        self._registrations: dict[str, RegisteredAgent] = {}

    def register(self, spec: AgentSpec, builder: AgentBuilder) -> None:
        """校验并登记一个唯一的 Agent 定义和构造器。"""

        self._validator.validate_spec(spec)
        if not callable(builder):
            raise TypeError("Agent Builder 必须可调用")
        if spec.agent_id in self._registrations:
            raise AgentRegistrationConflictError(f"Agent ID 已注册: {spec.agent_id}")
        self._registrations[spec.agent_id] = RegisteredAgent(spec, builder)

    def get(self, agent_id: str) -> RegisteredAgent:
        """按 Agent ID 返回注册项；不存在时失败关闭。"""

        try:
            return self._registrations[agent_id]
        except KeyError as error:
            raise AgentNotFoundError(f"Agent 不存在: {agent_id}") from error

    def match(
        self,
        requirement: CapabilityRequirement,
        *,
        kind: AgentKind | None = None,
    ) -> Sequence[RegisteredAgent]:
        """返回满足能力条件且按 Agent ID 稳定排序的注册项。"""

        matches = []
        for registration in self._registrations.values():
            spec = registration.spec
            if kind is not None and spec.kind is not kind:
                continue
            if not requirement.all_of.issubset(spec.capability_ids):
                continue
            if requirement.any_of and spec.capability_ids.isdisjoint(
                requirement.any_of
            ):
                continue
            matches.append(registration)
        return tuple(sorted(matches, key=lambda item: item.spec.agent_id))

    def snapshot(self) -> Mapping[str, RegisteredAgent]:
        """返回当前注册项的不可修改副本。"""

        return MappingProxyType(dict(self._registrations))
