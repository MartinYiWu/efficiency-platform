"""S6 场景生产包的依赖和外部副作用准入守卫。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_ROOT = (
    PROJECT_ROOT
    / "src"
    / "efficiency_platform_agent"
    / "agents"
    / "operation"
    / "scenarios"
)


class ScenarioSupervisorContractTests(unittest.TestCase):
    """场景层只能依赖稳定契约，不能持有运行时或外部适配器。"""

    def test_scenario_production_dependencies_are_governed(self) -> None:
        if not SCENARIO_ROOT.exists():
            self.skipTest("S6 场景包尚未创建")
        forbidden = {"langgraph", "httpx", "providers", "tools", "persistence", "api"}
        offenders: list[str] = []
        for path in SCENARIO_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                names = (
                    ([module] if module else [])
                    if isinstance(node, ast.ImportFrom)
                    else (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else []
                    )
                )
                for imported in names:
                    if imported and (
                        imported.split(".", 1)[0] in forbidden
                        or "specialists" in imported.split(".")
                    ):
                        offenders.append(f"{path}:{imported}")
        self.assertEqual(offenders, [])

    def test_scenario_production_has_no_sample_or_expected_result_symbols(self) -> None:
        if not SCENARIO_ROOT.exists():
            self.skipTest("S6 场景包尚未创建")
        forbidden = (
            "ScenarioSample",
            "expected_completion_status",
            "expected_deliverable_ids",
        )
        offenders = [
            f"{path}:{token}"
            for path in SCENARIO_ROOT.rglob("*.py")
            for token in forbidden
            if token in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])


__all__ = ["ScenarioSupervisorContractTests"]
