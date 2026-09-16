import ast
from pathlib import Path


def test_s7_control_plane_does_not_add_clients_or_external_io():
    root = (
        Path(__file__).parents[2]
        / "src"
        / "efficiency_platform_agent"
        / "configuration"
    )
    forbidden = {"httpx", "openai", "sqlalchemy", "redis", "qcloud_cos", "langgraph"}
    imports = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports.extend(
            node.names[0].name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import) and node.names
        )
        imports.extend(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
    assert not any(item.split(".")[0] in forbidden for item in imports)
