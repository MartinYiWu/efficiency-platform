"""S5B 品牌、IP、产品 Specialist 的离线固定契约测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.specialists.brand import (
    BrandOperationAgent,
)
from efficiency_platform_agent.agents.operation.specialists.ip import IPOperationAgent
from efficiency_platform_agent.agents.operation.specialists.product import (
    ProductOperationAgent,
)


class BrandIpProductSpecialistTests(unittest.TestCase):
    """确认三个策略 Specialist 拥有独立稳定身份。"""

    def test_three_specialists_expose_distinct_typed_definitions(self) -> None:
        agents = (BrandOperationAgent(), IPOperationAgent(), ProductOperationAgent())
        self.assertEqual(
            tuple(agent.spec.agent_id for agent in agents),
            (
                "operation.brand.strategy",
                "operation.ip.strategy",
                "operation.product.plan",
            ),
        )
        self.assertEqual(
            tuple(next(iter(agent.spec.capability_ids)) for agent in agents),
            tuple(
                item.value
                for item in (
                    OperationSpecialistCapabilityId.BRAND_STRATEGY,
                    OperationSpecialistCapabilityId.IP_STRATEGY,
                    OperationSpecialistCapabilityId.PRODUCT_PLAN,
                )
            ),
        )

    def test_agents_do_not_advertise_write_tools_or_permissions(self) -> None:
        for agent in (
            BrandOperationAgent(),
            IPOperationAgent(),
            ProductOperationAgent(),
        ):
            self.assertEqual(agent.spec.allowed_tools, frozenset())
            self.assertEqual(agent.spec.permissions, frozenset())


__all__ = ["BrandIpProductSpecialistTests"]
