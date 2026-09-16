"""S5B 三类运营 Specialist 的固定样本验收。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from efficiency_platform_agent.agents.operation.specialists.brand import (
    BrandOperationAgent,
)
from efficiency_platform_agent.agents.operation.specialists.ip import IPOperationAgent
from efficiency_platform_agent.agents.operation.specialists.product import (
    ProductOperationAgent,
)


class OperationBrandIpProductAcceptanceTests(unittest.TestCase):
    def test_fixed_samples_map_to_distinct_strategy_deliverables(self) -> None:
        root = Path(__file__).parents[1] / "fixtures" / "operation"
        agents = (
            (BrandOperationAgent(), root / "brand" / "brand_launch_v1.json"),
            (IPOperationAgent(), root / "ip" / "knowledge_creator_v1.json"),
            (ProductOperationAgent(), root / "product" / "product_launch_v1.json"),
        )
        labels: list[str] = []
        for agent, fixture in agents:
            sample = json.loads(fixture.read_text(encoding="utf-8"))
            result = agent.build_result(
                SimpleNamespace(task_id="task-a", operation_context=None)
            )
            bundle = result.deliverable_bundle
            assert bundle is not None
            payload = dict(bundle.deliverables[0].payload.items)
            labels.append(payload["deliverable_kind"])
            self.assertEqual(payload["deliverable_kind"], sample["expected_kind"])
        self.assertEqual(
            tuple(labels), ("brand_strategy", "ip_strategy", "product_operation_plan")
        )


__all__ = ["OperationBrandIpProductAcceptanceTests"]
