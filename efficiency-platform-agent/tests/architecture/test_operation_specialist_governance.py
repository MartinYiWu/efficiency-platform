"""S5 运营 Specialist 的依赖和协作边界守卫。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPERATION_ROOT = (
    PROJECT_ROOT / "src" / "efficiency_platform_agent" / "agents" / "operation"
)


def _imports(path: Path) -> tuple[str, ...]:
    """提取文件中的绝对和相对导入模块。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return tuple(modules)


class OperationSpecialistGovernanceTests(unittest.TestCase):
    """确保运营 Specialist 只通过稳定端口工作。"""

    def test_specialist_code_has_no_external_or_write_dependencies(self) -> None:
        forbidden = {
            "httpx",
            "openai",
            "dashscope",
            "polars",
            "fastexcel",
            "sqlalchemy",
            "redis",
            "psycopg",
            "cos_python_sdk_v5",
        }
        offenders = [
            f"{path}:{module}"
            for path in OPERATION_ROOT.rglob("*.py")
            for module in _imports(path)
            if module.split(".", 1)[0] in forbidden
        ]
        self.assertEqual(offenders, [])

    def test_specialist_code_does_not_import_supervisor_registry_or_factory(
        self,
    ) -> None:
        root = OPERATION_ROOT / "specialists"
        if not root.exists():
            self.skipTest("S5 Specialist 尚未创建")
        forbidden_layers = {"supervisor", "registry", "factory"}
        offenders = [
            f"{path}:{module}"
            for path in root.rglob("*.py")
            for module in _imports(path)
            if any(layer in module.split(".") for layer in forbidden_layers)
        ]
        self.assertEqual(offenders, [])

    def test_specialist_code_contains_no_platform_send_or_contact_actions(self) -> None:
        forbidden_tokens = (
            "send_message",
            "publish_to_platform",
            "publish_content",
            "notify_user",
            "place_order",
        )
        offenders: list[str] = []
        for path in (OPERATION_ROOT / "specialists").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in source:
                    offenders.append(f"{path}:{token}")
        self.assertEqual(offenders, [])


__all__ = ["OperationSpecialistGovernanceTests"]
