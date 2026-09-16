"""S2 依赖准入与禁止组件门禁。"""

import importlib.metadata
import sys
import unittest


class S2DependenciesTest(unittest.TestCase):
    """验证 S2 允许的运行时和开发工具依赖边界。"""

    def test_s2_required_distributions_are_installed(self) -> None:
        """所有 S2 必需 distribution 都应可由当前环境解析。"""
        required = (
            "fastapi",
            "pydantic",
            "uvicorn",
            "jinja2",
            "langgraph",
            "pytest",
            "pytest-asyncio",
            "httpx",
            "ruff",
            "mypy",
        )

        missing = [name for name in required if not _distribution_exists(name)]

        self.assertEqual([], missing, f"缺少 S2 必需 distribution: {missing}")

    def test_s2_forbidden_distributions_are_not_installed(self) -> None:
        """禁止组件 distribution 不得进入 S2 环境。"""
        forbidden = (
            "langchain",
            "autogen-agentchat",
            "crewai",
            "llama-index-core",
            "alembic",
            "opentelemetry-sdk",
            "prometheus-client",
        )

        installed = [name for name in forbidden if _distribution_exists(name)]

        self.assertEqual([], installed, f"发现 S2 禁止 distribution: {installed}")

    def test_python_version_is_313(self) -> None:
        """S2 只能在 Python 3.13 解释器上运行。"""
        self.assertEqual((3, 13), sys.version_info[:2])


def _distribution_exists(name: str) -> bool:
    """以不抛异常的方式判断 distribution 是否存在。"""
    try:
        importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


if __name__ == "__main__":
    unittest.main()
