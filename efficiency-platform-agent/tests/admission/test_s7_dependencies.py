"""S7 依赖声明的离线准入检查，不安装或导入真实集成组件。"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVED = {
    "openai",
    "pydantic-settings",
    "sqlalchemy",
    "psycopg",
    "pgvector",
    "langgraph-checkpoint-postgres",
    "redis",
    "taskiq",
    "taskiq-redis",
    "cos-python-sdk-v5",
    "python-multipart",
    "puremagic",
    "pypdf",
    "pypdfium2",
    "pillow",
    "defusedxml",
    "nh3",
    "charset-normalizer",
    "docling",
    "paddleocr",
    "paddlepaddle",
    "semantic-text-splitter",
    "polars",
    "fastexcel",
}
FORBIDDEN = {
    "autogen",
    "crewai",
    "langchain",
    "langchain-openai",
    "llama-index",
    "playwright",
    "beautifulsoup4",
    "trafilatura",
    "duckdb",
    "sqlglot",
    "openpyxl",
    "ragas",
    "deepeval",
}


def _declared_dependencies() -> set[str]:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {
        re.split(r"[<>=!~;\[]", item, maxsplit=1)[0].strip().lower()
        for item in document["project"]["dependencies"]
    }


def test_python_version_is_313() -> None:
    assert sys.version_info[:2] == (3, 13)
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert document["project"]["requires-python"] == ">=3.13,<3.14"


def test_forbidden_packages_are_not_declared() -> None:
    declared = _declared_dependencies()
    assert declared.isdisjoint(FORBIDDEN)


def test_approved_s7_packages_are_declared_and_locked() -> None:
    declared = _declared_dependencies()
    lock_text = (ROOT / "uv.lock").read_text(encoding="utf-8")
    missing = sorted(
        name
        for name in APPROVED
        if name not in declared or f'name = "{name}"' not in lock_text
    )
    assert not missing, f"S7 依赖尚未声明或锁定: {missing}"
