"""S4 多 Agent 调度的架构守卫。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "efficiency_platform_agent"


def _imports(path: Path) -> tuple[str, ...]:
    """提取源码中显式声明的导入模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


class MultiAgentGovernanceTests(unittest.TestCase):
    """拒绝点对点 Agent、第二运行时和 S4 外部 I/O。"""

    def test_multi_agent_strategy_has_no_graph_framework_import(self) -> None:
        strategy_root = SRC_ROOT / "strategies" / "multi_agent"
        imports = tuple(
            module for path in strategy_root.rglob("*.py") for module in _imports(path)
        )
        forbidden = {"langgraph", "autogen", "crewai", "llama_index", "temporalio"}
        self.assertFalse(
            any(module.split(".", 1)[0] in forbidden for module in imports)
        )

    def test_only_orchestration_imports_langgraph(self) -> None:
        offenders: list[str] = []
        for path in (PROJECT_ROOT / "src").rglob("*.py"):
            relative_parts = path.relative_to(PROJECT_ROOT / "src").parts
            for module in _imports(path):
                if (
                    module.split(".", 1)[0] == "langgraph"
                    and "orchestration" not in relative_parts
                ):
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_s4_production_does_not_import_external_io_adapters(self) -> None:
        roots = (
            SRC_ROOT / "agents" / "operation" / "supervisor",
            SRC_ROOT / "strategies" / "multi_agent",
        )
        forbidden = {
            "httpx",
            "openai",
            "dashscope",
            "redis",
            "psycopg",
            "sqlalchemy",
            "cos_python_sdk_v5",
            "socket",
        }
        offenders = [
            f"{path.relative_to(PROJECT_ROOT)}:{module}"
            for root in roots
            for path in root.rglob("*.py")
            for module in _imports(path)
            if module.split(".", 1)[0] in forbidden
        ]
        self.assertEqual(offenders, [])

    def test_s4_does_not_hardcode_business_agent_routing(self) -> None:
        """业务 Agent 必须通过能力匹配，不能以 ID 或类名写条件分支。"""

        roots = (
            SRC_ROOT / "agents" / "operation" / "supervisor",
            SRC_ROOT / "strategies" / "multi_agent",
        )
        offenders: list[str] = []
        for root in roots:
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                if "agent_id ==" in source or "agent_id in" in source:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
                if "specialists." in source:
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_specialist_directory_is_not_a_peer_to_peer_dispatch_surface(self) -> None:
        specialist_root = SRC_ROOT / "agents" / "operation" / "specialists"
        if not specialist_root.exists():
            return
        forbidden = {"registry", "factory", "supervisor"}
        offenders = [
            f"{path.relative_to(PROJECT_ROOT)}:{module}"
            for path in specialist_root.rglob("*.py")
            for module in _imports(path)
            if any(layer in module.split(".") for layer in forbidden)
        ]
        self.assertEqual(offenders, [])


__all__ = ["MultiAgentGovernanceTests"]
