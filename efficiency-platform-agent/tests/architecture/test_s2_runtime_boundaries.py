import ast
from pathlib import Path


def test_langgraph_imports_are_confined_to_orchestration() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "efficiency_platform_agent"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        outside = "orchestration" not in path.relative_to(root).parts
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if outside:
                assert not any(
                    name.startswith(("langgraph", "langchain.agents")) for name in names
                ), path
