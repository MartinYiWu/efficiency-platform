from __future__ import annotations

from efficiency_platform_agent.core.ports import AgentPlugin

from .errors import AgentAssemblyError, AgentDefinitionError
from .registry import AgentRegistry
from .validation import AgentValidator


class AgentFactory:
    """从显式注册定义创建并校验 AgentPlugin。"""

    def __init__(
        self,
        registry: AgentRegistry,
        validator: AgentValidator | None = None,
    ) -> None:
        self._registry = registry
        self._validator = validator or AgentValidator()

    def create(self, agent_id: str) -> AgentPlugin:
        """按固定顺序查找、构建、校验并返回 Agent 实例。"""

        registration = self._registry.get(agent_id)
        try:
            plugin = registration.builder()
        except Exception as error:
            raise AgentAssemblyError(f"Agent 装配失败: {agent_id}") from error
        try:
            self._validator.validate_instance(registration.spec, plugin)
        except AgentDefinitionError as error:
            raise AgentAssemblyError(f"Agent 实例校验失败: {agent_id}") from error
        return plugin
