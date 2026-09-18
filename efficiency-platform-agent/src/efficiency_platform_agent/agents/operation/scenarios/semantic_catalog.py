"""从真实运营注册声明构造只读 Intent V2 语义目录。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from efficiency_platform_agent.agents.operation.contracts.scenarios import (
    ScenarioPackManifest,
)
from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
    operation_agent_specs,
    operation_capability_specs,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.contracts.intent_v2 import (
    CapabilityCatalogSnapshot,
    CapabilityDescriptorV2,
)
from efficiency_platform_agent.core.agent import AgentSpec, CapabilitySpec


@dataclass(frozen=True, slots=True)
class OperationSemanticRegistryView:
    """真实注册声明的不可变投影视图，不拥有执行注册能力。"""

    capabilities: tuple[CapabilitySpec, ...]
    agents: tuple[AgentSpec, ...]
    manifests: tuple[ScenarioPackManifest, ...]


@dataclass(frozen=True, slots=True)
class _SemanticText:
    description: str
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]


_SEMANTIC_TEXT: dict[str, _SemanticText] = {
    OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value: _SemanticText(
        "基于受治理公开来源收集、整理并形成可追溯研究洞察。",
        ("收集上周 AI 行业动态并给出来源",),
        ("直接写一条无需事实核验的欢迎语",),
    ),
    OperationSpecialistCapabilityId.QUALITY_REVIEW.value: _SemanticText(
        "对已有运营交付物执行证据、完整性和质量复核。",
        ("检查这份研究简报的证据是否充分",),
        ("代替研究阶段凭空补齐新闻",),
    ),
    OperationSpecialistCapabilityId.BRAND_STRATEGY.value: _SemanticText(
        "形成品牌定位、目标和阶段策略方案。",
        ("为新品牌制定三个月运营策略",),
        ("只改写一条小红书标题",),
    ),
    OperationSpecialistCapabilityId.IP_STRATEGY.value: _SemanticText(
        "形成 IP 定位、受众和孵化策略。",
        ("设计创始人 IP 的内容定位",),
        ("分析一份结构化数据表",),
    ),
    OperationSpecialistCapabilityId.PRODUCT_PLAN.value: _SemanticText(
        "形成产品运营目标、节奏和行动计划。",
        ("制定新品上市运营计划",),
        ("在线检索当天新闻",),
    ),
    OperationSpecialistCapabilityId.CONTENT_CREATE.value: _SemanticText(
        "基于明确主题和约束生成通用内容或内容日历。",
        ("生成一个月的内容日历",),
        ("验证外部新闻是否真实",),
    ),
    OperationSpecialistCapabilityId.CHANNEL_CONTENT.value: _SemanticText(
        "将已确定材料适配为指定渠道的独立成品。",
        ("把研究结果分别写成公众号和小红书稿",),
        ("把目标平台当作新闻来源",),
    ),
    OperationSpecialistCapabilityId.CAMPAIGN_PLAN.value: _SemanticText(
        "形成活动目标、受众、节奏和执行计划。",
        ("策划一次新品发布活动",),
        ("复核季度经营指标",),
    ),
    OperationSpecialistCapabilityId.USER_GROWTH_PLAN.value: _SemanticText(
        "形成增长目标、漏斗阶段和实验计划。",
        ("设计注册转化率增长实验",),
        ("生成品牌视觉素材",),
    ),
    OperationSpecialistCapabilityId.COMMUNITY_PLAN.value: _SemanticText(
        "形成社群运营、互动和留存计划。",
        ("设计用户社群月度运营计划",),
        ("抓取全球实时热点",),
    ),
    OperationSpecialistCapabilityId.ANALYTICS_REVIEW.value: _SemanticText(
        "基于授权分析数据形成指标复盘和改进建议。",
        ("复盘上月运营指标并解释变化",),
        ("在没有数据时伪造增长结论",),
    ),
}


def build_operation_semantic_registry_view() -> OperationSemanticRegistryView:
    """读取现有唯一来源，构造不含运行时实例的投影视图。"""
    return OperationSemanticRegistryView(
        capabilities=operation_capability_specs(),
        agents=operation_agent_specs(),
        manifests=build_s6_manifests(),
    )


def build_operation_semantic_catalog() -> CapabilityCatalogSnapshot:
    return build_semantic_catalog(build_operation_semantic_registry_view())


def build_semantic_catalog(
    registry: OperationSemanticRegistryView,
) -> CapabilityCatalogSnapshot:
    """从真实注册版本/权限/Schema/Manifest 导出稳定语义快照。"""
    if not isinstance(registry, OperationSemanticRegistryView):
        raise TypeError("registry 必须是 OperationSemanticRegistryView")
    capability_by_id = _unique_capabilities(registry.capabilities)
    agent_by_capability = _unique_agents(registry.agents)
    canonical_ids = {item.value for item in OperationSpecialistCapabilityId}
    if set(capability_by_id) != canonical_ids or set(_SEMANTIC_TEXT) != canonical_ids:
        raise ValueError("SEMANTIC_CATALOG_CAPABILITY_DRIFT")
    if not canonical_ids.issubset(agent_by_capability):
        raise ValueError("SEMANTIC_CATALOG_AGENT_MISSING")
    outputs, prerequisites = _manifest_projection(registry.manifests)
    descriptors = tuple(
        _descriptor(
            capability_by_id[capability_id],
            agent_by_capability[capability_id],
            outputs.get(capability_id, ()),
            prerequisites.get(capability_id, ()),
        )
        for capability_id in sorted(canonical_ids)
    )
    canonical = json.dumps(
        [item.model_dump(mode="json") for item in descriptors],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return CapabilityCatalogSnapshot(
        catalog_version=f"operation-semantic/{digest}",
        capabilities=descriptors,
    )


def _descriptor(
    capability: CapabilitySpec,
    agent: AgentSpec,
    outputs: tuple[str, ...],
    prerequisites: tuple[str, ...],
) -> CapabilityDescriptorV2:
    metadata = _SEMANTIC_TEXT[capability.capability_id]
    projected_outputs = outputs or (agent.output_schema_version,)
    return CapabilityDescriptorV2(
        capability_id=capability.capability_id,
        version=capability.semantic_version,
        description=metadata.description,
        parameter_schema_ref=(
            f"operation-intent-parameters/{capability.capability_id}/1"
        ),
        required_permissions=tuple(sorted(capability.permissions)),
        positive_examples=metadata.positive_examples,
        negative_examples=metadata.negative_examples,
        supported_outputs=projected_outputs,
        prerequisites=prerequisites,
    )


def _unique_capabilities(
    capabilities: tuple[CapabilitySpec, ...],
) -> dict[str, CapabilitySpec]:
    result = {item.capability_id: item for item in capabilities}
    if len(result) != len(capabilities):
        raise ValueError("SEMANTIC_CATALOG_CAPABILITY_DUPLICATED")
    return result


def _unique_agents(agents: tuple[AgentSpec, ...]) -> dict[str, AgentSpec]:
    result: dict[str, AgentSpec] = {}
    for agent in agents:
        for capability_id in agent.capability_ids:
            if capability_id in result:
                raise ValueError("SEMANTIC_CATALOG_AGENT_DUPLICATED")
            result[capability_id] = agent
    return result


def _manifest_projection(
    manifests: tuple[ScenarioPackManifest, ...],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    outputs: dict[str, set[str]] = {}
    prerequisites: dict[str, set[str]] = {}
    for manifest in manifests:
        manifest_capabilities = {
            capability_id
            for step in manifest.plan_template.steps
            for capability_id in (
                step.required_capabilities.all_of
                | step.required_capabilities.any_of
            )
        }
        # 清单级交付要求是生产声明。只有单能力场景才能无歧义归属；
        # 多能力场景保留步骤输出契约版本，不能把测试期望字段当能力事实。
        if len(manifest_capabilities) == 1:
            only_capability = next(iter(manifest_capabilities))
            outputs.setdefault(only_capability, set()).update(
                item.requirement_id for item in manifest.output_requirements
            )
        step_by_id = {
            step.step_id: step for step in manifest.plan_template.steps
        }
        for step in manifest.plan_template.steps:
            capability_ids = (
                step.required_capabilities.all_of
                | step.required_capabilities.any_of
            )
            dependency_capabilities = {
                capability_id
                for dependency_id in step.depends_on_step_ids
                for capability_id in (
                    step_by_id[dependency_id].required_capabilities.all_of
                    | step_by_id[dependency_id].required_capabilities.any_of
                )
            }
            for capability_id in capability_ids:
                outputs.setdefault(capability_id, set()).add(
                    step.output_schema_version
                )
                prerequisites.setdefault(capability_id, set()).update(
                    dependency_capabilities
                )
    return (
        {key: tuple(sorted(value)) for key, value in outputs.items()},
        {key: tuple(sorted(value)) for key, value in prerequisites.items()},
    )


__all__ = [
    "OperationSemanticRegistryView",
    "build_operation_semantic_catalog",
    "build_operation_semantic_registry_view",
    "build_semantic_catalog",
]
