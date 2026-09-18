"""Prompt Bundle 的显式注册表。"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from .contracts import PromptBundleSpec


class PromptRegistry:
    """仅允许调用方显式登记 Prompt，不执行动态扫描或导入。"""

    def __init__(self) -> None:
        self._specs: dict[str, PromptBundleSpec] = {}

    def register(self, spec: PromptBundleSpec) -> None:
        """登记唯一 Prompt ID。"""
        if not isinstance(spec, PromptBundleSpec):
            raise TypeError("spec 必须为 PromptBundleSpec")
        if spec.prompt_id in self._specs:
            raise ValueError(f"重复 Prompt ID: {spec.prompt_id}")
        self._specs[spec.prompt_id] = spec

    def get(self, prompt_id: str) -> PromptBundleSpec:
        """获取已登记 Prompt，未登记时失败关闭。"""
        try:
            return self._specs[prompt_id]
        except KeyError as exc:
            raise KeyError(f"未注册 Prompt: {prompt_id}") from exc

    def snapshot(self) -> Mapping[str, PromptBundleSpec]:
        """返回不可变登记快照。"""
        return MappingProxyType(dict(self._specs))


def register_intent_v2_prompts(registry: PromptRegistry) -> None:
    """显式登记 Intent V2 的解释、修复和复核 Prompt。"""
    if not isinstance(registry, PromptRegistry):
        raise TypeError("registry 必须为 PromptRegistry")
    specs = (
        PromptBundleSpec(
            prompt_id="intent.v2.interpret",
            semantic_version="1.0.0",
            owner="intent-v2",
            template_path="intent/interpret_v2.j2",
            variable_schema_version="intent-v2-prompt-vars/1",
            required_variables=frozenset(
                {"capability_catalog", "field_schema", "context_manifest"}
            ),
            output_schema_version="intent-patch/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=120_000,
        ),
        PromptBundleSpec(
            prompt_id="intent.v2.repair",
            semantic_version="1.0.0",
            owner="intent-v2",
            template_path="intent/repair_v2.j2",
            variable_schema_version="intent-v2-prompt-vars/1",
            required_variables=frozenset({"field_schema", "validation_error"}),
            output_schema_version="intent-patch/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=80_000,
        ),
        PromptBundleSpec(
            prompt_id="intent.v2.review",
            semantic_version="1.0.0",
            owner="intent-v2",
            template_path="intent/review_v2.j2",
            variable_schema_version="intent-v2-prompt-vars/1",
            required_variables=frozenset({"capability_catalog", "field_schema"}),
            output_schema_version="intent-patch/2",
            allowed_model_tiers=frozenset({"strong"}),
            max_rendered_chars=120_000,
        ),
    )
    for spec in specs:
        registry.register(spec)


def register_research_v2_prompts(registry: PromptRegistry) -> None:
    """显式登记 Research V2 各阶段的受治理 Prompt。"""
    if not isinstance(registry, PromptRegistry):
        raise TypeError("registry 必须为 PromptRegistry")
    specs = (
        PromptBundleSpec(
            prompt_id="research.v2.relevance",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/relevance_v2.j2",
            variable_schema_version="research-relevance-prompt-vars/1",
            required_variables=frozenset({"brief_schema", "decision_schema"}),
            output_schema_version="semantic-relevance-decision/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=80_000,
        ),
        PromptBundleSpec(
            prompt_id="research.v2.cluster",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/cluster_v2.j2",
            variable_schema_version="research-cluster-prompt-vars/1",
            required_variables=frozenset({"brief_schema", "proposal_schema"}),
            output_schema_version="cluster-proposal/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=80_000,
        ),
        PromptBundleSpec(
            prompt_id="research.v2.claims",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/claims_v2.j2",
            variable_schema_version="research-claims-prompt-vars/1",
            required_variables=frozenset(
                {"claim_schema", "evidence_schema", "event_schema"}
            ),
            output_schema_version="claim-proposal/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=100_000,
        ),
        PromptBundleSpec(
            prompt_id="research.v2.replan",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/replan_v2.j2",
            variable_schema_version="research-replan-prompt-vars/1",
            required_variables=frozenset(
                {"action_policy", "brief_schema", "plan_schema", "quality_schema"}
            ),
            output_schema_version="collection-plan/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=100_000,
        ),
        PromptBundleSpec(
            prompt_id="research.v2.compose",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/compose_v2.j2",
            variable_schema_version="research-compose-prompt-vars/1",
            required_variables=frozenset(
                {"brief_schema", "draft_schema", "evidence_schema"}
            ),
            output_schema_version="delivery-draft/2",
            allowed_model_tiers=frozenset({"balanced", "strong"}),
            max_rendered_chars=120_000,
        ),
        PromptBundleSpec(
            prompt_id="research.v2.verify",
            semantic_version="1.0.0",
            owner="research-v2",
            template_path="research/verify_v2.j2",
            variable_schema_version="research-verify-prompt-vars/1",
            required_variables=frozenset(
                {"decision_schema", "draft_schema", "evidence_schema"}
            ),
            output_schema_version="output-decision/2",
            allowed_model_tiers=frozenset({"strong"}),
            max_rendered_chars=120_000,
        ),
    )
    for spec in specs:
        registry.register(spec)


__all__ = [
    "PromptRegistry",
    "register_intent_v2_prompts",
    "register_research_v2_prompts",
]
