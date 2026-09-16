"""基于注册元数据选择 Specialist，并裁剪可委派上下文。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from efficiency_platform_agent.agents.registry import RegisteredAgent
from efficiency_platform_agent.core.agent import AgentSpec, CapabilityRequirement
from efficiency_platform_agent.core.enums import AgentKind
from efficiency_platform_agent.core.multi_agent import TaskNode
from efficiency_platform_agent.core.run import JsonObject, JsonValue

from ..contracts.profiles import OperationContext, ProfileReference
from ..contracts.task import SourceScope


class _SpecialistRegistry(Protocol):
    """选择器所需的最小注册表只读能力。"""

    def match(
        self,
        requirement: CapabilityRequirement,
        *,
        kind: AgentKind | None = None,
    ) -> Sequence[RegisteredAgent]:
        """返回声明满足能力条件的注册项。"""


@dataclass(frozen=True, slots=True)
class SelectedSpecialist:
    """经过硬过滤但尚未装配实例的 Specialist 注册元数据。"""

    agent_id: str
    spec: AgentSpec

    def __post_init__(self) -> None:
        if self.agent_id != self.spec.agent_id:
            raise ValueError("候选 Agent 标识与注册元数据不一致")


def _matches_capabilities(requirement: CapabilityRequirement, spec: AgentSpec) -> bool:
    """重复执行能力匹配，避免注册表替换实现时放宽治理语义。"""
    return requirement.all_of.issubset(spec.capability_ids) and (
        not requirement.any_of or not spec.capability_ids.isdisjoint(requirement.any_of)
    )


def _can_execute_once(spec: AgentSpec) -> bool:
    """确认注册 Agent 至少允许一次迭代和非零超时的执行。"""
    return spec.budget.max_iterations >= 1 and spec.budget.timeout_ms >= 1


class SpecialistSelector:
    """只按 S1/S3 治理元数据选择候选，不创建任何 Agent 实例。"""

    def __init__(self, registry: _SpecialistRegistry) -> None:
        self._registry = registry

    def rank(self, node: TaskNode) -> tuple[SelectedSpecialist, ...]:
        """返回满足六项硬条件且按稳定评分排序的候选。"""
        if not isinstance(node, TaskNode):
            raise TypeError("node 必须是 TaskNode")
        registrations = self._registry.match(
            node.capability_requirement,
            kind=AgentKind.SPECIALIST,
        )
        candidates: list[SelectedSpecialist] = []
        for registration in registrations:
            spec = registration.spec
            if spec.kind is not AgentKind.SPECIALIST:
                continue
            if node.task_type not in spec.supported_task_types:
                continue
            if not _matches_capabilities(node.capability_requirement, spec):
                continue
            if node.input_schema_version != spec.input_schema_version:
                continue
            if node.output_schema_version != spec.output_schema_version:
                continue
            if not node.required_permissions.issubset(spec.permissions):
                continue
            if not node.allowed_tools.issubset(spec.allowed_tools):
                continue
            if not _can_execute_once(spec):
                continue
            candidates.append(SelectedSpecialist(spec.agent_id, spec))
        required_capabilities = (
            node.capability_requirement.all_of | node.capability_requirement.any_of
        )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    len(item.spec.capability_ids - required_capabilities),
                    len(item.spec.permissions - node.required_permissions),
                    len(item.spec.allowed_tools - node.allowed_tools),
                    item.spec.budget.max_cost_microunits,
                    item.agent_id,
                ),
            )
        )


class ContextProjector:
    """将 S3 最小运营上下文转为 Specialist 可消费的不可变 JSON。"""

    def project(
        self,
        context: OperationContext,
        *,
        profile_ids: tuple[str, ...],
        source_scopes: frozenset[SourceScope] | None = None,
    ) -> JsonObject:
        """仅投影请求的 Profile 引用和来源范围，缺失即失败关闭。"""
        if not isinstance(context, OperationContext):
            raise TypeError("context 必须是 OperationContext")
        if not isinstance(profile_ids, tuple):
            raise TypeError("profile_ids 必须是不可变元组")
        if len(set(profile_ids)) != len(profile_ids):
            raise ValueError("profile_ids 不得重复")
        if source_scopes is None:
            source_scopes = context.source_scope_ids
        if not isinstance(source_scopes, frozenset):
            raise TypeError("source_scopes 必须是不可变集合")
        if not source_scopes.issubset(context.source_scope_ids):
            raise ValueError("请求来源范围不在运营上下文中")
        known_profiles = {item.profile_id: item for item in context.profile_references}
        if any(profile_id not in known_profiles for profile_id in profile_ids):
            raise ValueError("请求的 Profile 引用不存在")
        profiles = tuple(
            self._profile_json(known_profiles[profile_id]) for profile_id in profile_ids
        )
        return JsonObject(
            (
                ("context_id", context.context_id),
                ("tenant_id", context.tenant_id),
                ("task_id", context.task_id),
                ("profile_references", profiles),
                (
                    "source_scope_ids",
                    tuple(sorted(item.value for item in source_scopes)),
                ),
            )
        )

    @staticmethod
    def _profile_json(reference: ProfileReference) -> tuple[JsonValue, ...]:
        """把版本化 Profile 引用转换为新的不可变元组。"""
        return (
            reference.profile_id,
            reference.kind.value,
            reference.semantic_version,
            reference.fact_ids,
        )


__all__ = ["ContextProjector", "SelectedSpecialist", "SpecialistSelector"]
