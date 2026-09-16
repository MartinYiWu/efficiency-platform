"""显式 Specialist 注册与能力目录离线集成测试。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from efficiency_platform_agent.agents.operation.definition import (
    operation_agent_specs,
    operation_specialist_capability_ids,
    register_operation_specialists,
)
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchProviderPort,
)


class _ResearchFake:
    """仅用于注册装配的最小研究端口替身。"""

    async def research(self, request):
        raise RuntimeError("集成测试不执行研究调用")


class SpecialistDispatchIntegrationTests(unittest.TestCase):
    def test_registers_eleven_specialists_with_one_capability_each(self) -> None:
        self.assertIsInstance(_ResearchFake(), ResearchProviderPort)
        registry = AgentRegistry()
        register_operation_specialists(
            registry,
            SimpleNamespace(research_provider=_ResearchFake(), analytics_reader=None),
        )
        snapshot = registry.snapshot()
        self.assertEqual(len(snapshot), 11)
        specs = operation_agent_specs()
        self.assertEqual(tuple(snapshot), tuple(spec.agent_id for spec in specs))
        self.assertTrue(all(len(spec.capability_ids) == 1 for spec in specs))

    def test_catalog_has_exactly_one_registered_owner_per_capability(self) -> None:
        registry = AgentRegistry()
        register_operation_specialists(
            registry,
            {"research_provider": _ResearchFake(), "analytics_reader": None},
        )
        for capability_id in operation_specialist_capability_ids():
            owners = tuple(
                item.spec.agent_id
                for item in registry.snapshot().values()
                if capability_id in item.spec.capability_ids
            )
            self.assertEqual(len(owners), 1)


__all__ = ["SpecialistDispatchIntegrationTests"]
