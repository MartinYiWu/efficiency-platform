from __future__ import annotations

import unittest
from pathlib import Path

from efficiency_platform_agent.orchestration.builders.operation_supervisor import (
    NODE_SEQUENCE,
    OperationSupervisorGraphBuilder,
)
from efficiency_platform_agent.strategies.multi_agent.nodes import (
    SupervisorDependencies,
)


class OperationSupervisorBuilderTests(unittest.TestCase):
    def test_sequence_contains_governed_nodes(self):
        self.assertEqual(
            NODE_SEQUENCE[:2], ("decode_operation_request", "normalize_intent")
        )
        self.assertIn("compile_plan", NODE_SEQUENCE)
        self.assertEqual(NODE_SEQUENCE[-1], "finalize")

    def test_builder_compiles_without_external_services(self):
        graph = OperationSupervisorGraphBuilder(
            SupervisorDependencies(None, None, None)
        ).build()
        self.assertTrue(hasattr(graph, "invoke"))

    def test_only_builder_imports_langgraph(self):
        root = Path(__file__).parents[4] / "src" / "efficiency_platform_agent"
        for path in (root / "strategies" / "multi_agent").glob("*.py"):
            self.assertFalse("langgraph" in path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
