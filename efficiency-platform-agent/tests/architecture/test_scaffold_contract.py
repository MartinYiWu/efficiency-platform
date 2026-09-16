from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))


class ScaffoldContractTest(unittest.TestCase):
    def test_required_agent_layers_are_importable(self) -> None:
        required_packages = (
            "api",
            "contracts",
            "conversation",
            "harness",
            "routing",
            "orchestration",
            "strategies",
            "agents",
            "workflows",
            "context",
            "memory",
            "prompts",
            "tools",
            "capabilities",
            "providers",
            "persistence",
            "tasks",
            "observability",
            "evaluation",
            "security",
            "core",
        )

        for package in required_packages:
            with self.subTest(package=package):
                importlib.import_module(f"efficiency_platform_agent.{package}")

    def test_supported_strategy_slots_are_importable(self) -> None:
        strategy_packages = (
            "direct",
            "workflow",
            "react",
            "plan_execute",
            "multi_agent",
        )

        for package in strategy_packages:
            with self.subTest(package=package):
                importlib.import_module(
                    f"efficiency_platform_agent.strategies.{package}"
                )

    def test_cross_cutting_extension_slots_are_importable(self) -> None:
        extension_packages = (
            "tools.runtime",
            "tools.internal",
            "tools.external",
            "tools.mcp",
            "capabilities.model",
            "capabilities.retrieval",
            "capabilities.document",
            "capabilities.ocr",
            "capabilities.research",
            "capabilities.analytics",
            "capabilities.citation",
            "capabilities.artifact",
            "providers.llm",
            "providers.embedding",
            "providers.rerank",
            "providers.ocr",
            "providers.storage",
            "providers.database",
            "providers.cache",
            "providers.search",
        )

        for package in extension_packages:
            with self.subTest(package=package):
                importlib.import_module(f"efficiency_platform_agent.{package}")


if __name__ == "__main__":
    unittest.main()
