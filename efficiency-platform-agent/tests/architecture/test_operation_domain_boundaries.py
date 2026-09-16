"""运营领域内核的依赖隔离和非执行边界测试。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _scan_python_imports(source_root: Path, forbidden_layers: set[str]) -> list[str]:
    """解析源码导入并返回命中的禁止层名称。"""
    violations: set[str] = set()
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.Import):
                for item in node.names:
                    module = item.name
                    for layer in forbidden_layers:
                        if layer in module.split("."):
                            violations.add(f"{path.relative_to(PROJECT_ROOT)}:{layer}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module is None:
                    continue
                for layer in forbidden_layers:
                    if layer in module.split("."):
                        violations.add(f"{path.relative_to(PROJECT_ROOT)}:{layer}")
    return sorted(violations)


class OperationDomainBoundaryTests(unittest.TestCase):
    """确认运营契约只保存领域值对象，不反向接入执行或外部适配器。"""

    def test_operation_contracts_do_not_import_execution_or_external_layers(
        self,
    ) -> None:
        source_root = (
            PROJECT_ROOT
            / "src"
            / "efficiency_platform_agent"
            / "agents"
            / "operation"
            / "contracts"
        )
        forbidden = {
            "harness",
            "strategies",
            "orchestration",
            "providers",
            "persistence",
            "tools",
            "workflows",
            "api",
        }
        self.assertEqual(_scan_python_imports(source_root, forbidden), [])

    def test_no_real_operation_execution_modules_exist(self) -> None:
        operation_root = (
            PROJECT_ROOT / "src" / "efficiency_platform_agent" / "agents" / "operation"
        )
        # S4/S5 已建设 Supervisor 和离线 Specialist；领域契约仍不得持有执行实现依赖。
        self.assertTrue((operation_root / "supervisor").is_dir())
        self.assertTrue((operation_root / "specialists").is_dir())
        self.assertTrue((operation_root / "profiles").is_dir())
        self.assertTrue((operation_root / "quality").is_dir())


__all__ = ["OperationDomainBoundaryTests"]
