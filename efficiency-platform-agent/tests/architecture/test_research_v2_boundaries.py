"""X03 Research V2 外部 I/O、依赖方向与唯一运行时守卫。"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "efficiency_platform_agent"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _imports(path: Path) -> tuple[str, ...]:
    names: list[str] = []
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names.extend(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return tuple(names)


def test_research_agents_and_graph_do_not_perform_external_io_or_parse_network_data() -> (
    None
):
    roots = (
        PACKAGE / "orchestration" / "research_v2",
        PACKAGE / "agents" / "operation",
    )
    forbidden = {
        "httpx",
        "requests",
        "aiohttp",
        "socket",
        "openai",
        "feedparser",
        "trafilatura",
        "urllib3",
    }
    offenders = [
        f"{path.relative_to(ROOT)}:{module}"
        for root in roots
        for path in root.rglob("*.py")
        for module in _imports(path)
        if module.split(".", 1)[0] in forbidden
    ]
    assert offenders == []


def test_research_v2_has_one_state_graph_and_no_second_graph_runtime() -> None:
    root = PACKAGE / "orchestration" / "research_v2"
    state_graph_calls = 0
    graph_runtime_references: list[str] = []
    for path in root.rglob("*.py"):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                state_graph_calls += node.func.id == "StateGraph"
            if isinstance(node, ast.Name) and node.id == "GraphRuntime":
                graph_runtime_references.append(str(path.relative_to(ROOT)))
    assert state_graph_calls == 1
    assert graph_runtime_references == []


def test_research_v2_runtime_surfaces_have_no_dynamic_imports() -> None:
    roots = (
        PACKAGE / "orchestration" / "research_v2",
        PACKAGE / "capabilities" / "research" / "v2",
        PACKAGE / "providers" / "research",
    )
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            for node in ast.walk(_tree(path)):
                if not isinstance(node, ast.Call):
                    continue
                direct = (
                    isinstance(node.func, ast.Name) and node.func.id == "__import__"
                )
                indirect = (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                )
                if direct or indirect:
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_research_providers_do_not_depend_on_agent_or_orchestration_layers() -> None:
    forbidden_parts = {"agents", "orchestration", "harness", "conversation"}
    offenders = [
        f"{path.relative_to(ROOT)}:{module}"
        for path in (PACKAGE / "providers" / "research").rglob("*.py")
        for module in _imports(path)
        if module.startswith("efficiency_platform_agent.")
        and forbidden_parts.intersection(module.split("."))
    ]
    assert offenders == []
