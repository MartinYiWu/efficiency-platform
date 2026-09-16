"""S6 场景包 Registry 与八个 Manifest 的离线契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
    operation_agent_specs,
    operation_specialist_capability_ids,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.registry import (
    InMemoryScenarioPackRegistry,
)


class ScenarioPackRegistryTests(unittest.TestCase):
    """验证显式版本注册、稳定排序和跨阶段能力引用。"""

    def test_registry_returns_exactly_eight_v1_packs(self) -> None:
        registry = InMemoryScenarioPackRegistry(build_s6_manifests())
        pairs = tuple(
            (item.scenario_id, item.semantic_version) for item in registry.list()
        )
        self.assertEqual(len(pairs), 8)
        self.assertEqual(tuple(sorted(pairs)), pairs)
        self.assertTrue(all(version == "1.0.0" for _, version in pairs))

    def test_manifest_capabilities_use_s5_canonical_catalog(self) -> None:
        capabilities = set(operation_specialist_capability_ids())
        self.assertEqual(
            operation_specialist_capability_ids(),
            tuple(item.value for item in OperationSpecialistCapabilityId),
        )
        for manifest in build_s6_manifests():
            for step in manifest.plan_template.steps:
                self.assertTrue(step.required_capabilities.all_of <= capabilities)

    def test_registry_rejects_duplicate_and_requires_explicit_version(self) -> None:
        manifest = build_s6_manifests()[0]
        registry = InMemoryScenarioPackRegistry((manifest,))
        with self.assertRaises(ValueError):
            registry.register(manifest)
        with self.assertRaises(KeyError):
            registry.get(manifest.scenario_id, "2.0.0")

    def test_multi_platform_pack_has_three_independent_channel_steps(self) -> None:
        manifest = next(
            item
            for item in build_s6_manifests()
            if item.scenario_id == "multi_platform_content"
        )
        self.assertEqual(len(manifest.plan_template.steps), 3)
        outputs = tuple(
            output
            for step in manifest.plan_template.steps
            for output in step.expected_deliverable_ids
        )
        self.assertEqual(len(outputs), 3)
        self.assertEqual(len(set(outputs)), 3)
        self.assertTrue(
            all(
                step.task_type == "operation.channel_content"
                for step in manifest.plan_template.steps
            )
        )

    def test_channel_specialist_timeout_matches_multi_platform_step_budget(self) -> None:
        """多平台渠道专家不能被 30 秒旧上限提前取消。"""
        channel = next(
            item for item in operation_agent_specs()
            if item.agent_id == "operation.channel.content"
        )
        self.assertEqual(channel.budget.timeout_ms, 120_000)
        self.assertEqual(channel.budget.max_output_tokens, 8_000)


if __name__ == "__main__":
    unittest.main()
