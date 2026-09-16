from __future__ import annotations

from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.ports import AgentPlugin
from efficiency_platform_agent.core.run import ExtensionDescriptor

from .errors import AgentDefinitionError, AgentInstanceMismatchError


class AgentValidator:
    """在注册和装配边界执行失败关闭的 Agent 契约校验。"""

    def validate_spec(self, spec: AgentSpec) -> None:
        """拒绝不满足 AgentSpec 类型约束的注册定义。"""

        if not isinstance(spec, AgentSpec):
            raise AgentDefinitionError("Agent 定义必须是 AgentSpec")

    def validate_instance(self, spec: AgentSpec, plugin: AgentPlugin) -> None:
        """验证运行实例与注册定义的全部共享治理字段一致。"""

        self.validate_spec(spec)
        if not isinstance(plugin, AgentPlugin):
            raise AgentInstanceMismatchError("Agent 实例不满足 AgentPlugin 契约")
        if not isinstance(plugin.descriptor, ExtensionDescriptor):
            raise AgentInstanceMismatchError("Agent 实例的 descriptor 不满足 ExtensionDescriptor 契约")
        if plugin.spec != spec:
            raise AgentInstanceMismatchError("Agent 实例的 spec 与注册定义不一致")

        descriptor = plugin.descriptor
        comparisons = (
            ("agent_id", descriptor.name, spec.agent_id),
            ("semantic_version", descriptor.semantic_version, spec.semantic_version),
            (
                "input_schema_version",
                descriptor.input_schema_version,
                spec.input_schema_version,
            ),
            (
                "output_schema_version",
                descriptor.output_schema_version,
                spec.output_schema_version,
            ),
            ("permissions", descriptor.permissions, spec.permissions),
            ("budget", descriptor.budget, spec.budget),
            (
                "termination_conditions",
                descriptor.termination_conditions,
                spec.termination_conditions,
            ),
            (
                "checkpoint_version",
                descriptor.checkpoint_version,
                spec.checkpoint_version,
            ),
        )
        mismatches = tuple(
            field_name
            for field_name, actual, expected in comparisons
            if actual != expected
        )
        if mismatches:
            fields = ", ".join(mismatches)
            raise AgentInstanceMismatchError(
                f"Agent 实例与注册定义不一致: {fields}"
            )
