"""Static dependency guards for the pure Agent-side package."""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

PACKAGE_NAME = "efficiency_platform_agent"
_ROOT_PACKAGE_LAYER = "package"
_APPLICATION_ENTRY_LAYER = "application"

_ALLOWED_LAYER_DEPENDENCIES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        _ROOT_PACKAGE_LAYER: frozenset({"core", "contracts"}),
        # 正式启动入口仅负责装配组合根或在入口间转调。
        _APPLICATION_ENTRY_LAYER: frozenset({"harness", _APPLICATION_ENTRY_LAYER}),
        "core": frozenset({"core"}),
        # S4 的版本化运营载荷/恢复契约需要引用 S3 领域类型和 S2
        # CheckpointView；两者仍然是纯值对象，不引入运行时副作用。
        "contracts": frozenset({"core", "contracts", "agents", "orchestration"}),
        # 会话层只保存版本化输入和可见上下文，不拥有编排或运行生命周期。
        "conversation": frozenset(
            {
                "core",
                "contracts",
                "agents",
                "orchestration",
                "harness",
                "conversation",
            }
        ),
        "providers": frozenset({"core", "contracts", "providers"}),
        "persistence": frozenset({"core", "contracts", "providers", "persistence"}),
        "observability": frozenset({"core", "contracts", "observability"}),
        "security": frozenset({"core", "contracts", "security"}),
        "evaluation": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "observability",
                "evaluation",
            }
        ),
        "context": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "memory",
                "security",
                "observability",
                "context",
            }
        ),
        "memory": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "security",
                "observability",
                "memory",
            }
        ),
        "prompts": frozenset(
            {
                "core",
                "contracts",
                "persistence",
                "security",
                "observability",
                "prompts",
            }
        ),
        "tools": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "security",
                "observability",
                "tools",
            }
        ),
        "capabilities": frozenset(
            {
                "core",
                "contracts",
                # S5 Research 契约复用 S3 的 SourceScope 与证据值对象。
                "agents",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "security",
                "observability",
                "capabilities",
            }
        ),
        "agents": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "capabilities",
                "security",
                "observability",
                "agents",
            }
        ),
        "workflows": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "capabilities",
                "security",
                "observability",
                "workflows",
            }
        ),
        "strategies": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "capabilities",
                "security",
                "observability",
                "agents",
                "workflows",
                "routing",
                "strategies",
            }
        ),
        "orchestration": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "capabilities",
                "security",
                "observability",
                "agents",
                "workflows",
                "strategies",
                "routing",
                "conversation",
                "orchestration",
            }
        ),
        "routing": frozenset({"core", "contracts", "strategies", "routing"}),
        # runtime 只保存进程内传输状态，不拥有 Harness 或 Graph 生命周期。
        "runtime": frozenset({"core", "contracts", "runtime"}),
        "harness": frozenset(
            {
                "core",
                "contracts",
                "providers",
                "persistence",
                "context",
                "memory",
                "prompts",
                "tools",
                "capabilities",
                "security",
                "observability",
                "evaluation",
                "agents",
                "workflows",
                "strategies",
                "orchestration",
                "routing",
                "runtime",
                "api",
                "configuration",
                "conversation",
                "harness",
            }
        ),
        "api": frozenset(
            {
                "core",
                "contracts",
                "harness",
                "capabilities",
                "conversation",
                "runtime",
                "api",
            }
        ),
        "tasks": frozenset({"core", "contracts", "harness", "observability", "tasks"}),
        "configuration": frozenset({"core", "contracts", "configuration"}),
    }
)


def validate_dependencies(source_root: Path) -> tuple[str, ...]:
    """Return deterministic dependency violations found below ``source_root``."""

    package_root = source_root / PACKAGE_NAME
    if not package_root.is_dir():
        return (f"missing package root: {package_root}",)

    violations: list[str] = []
    for source_file in sorted(package_root.rglob("*.py")):
        relative_file = source_file.relative_to(package_root)
        importer_layer = _importer_layer(relative_file)
        if importer_layer not in _ALLOWED_LAYER_DEPENDENCIES:
            violations.append(
                f"{relative_file}: unknown importer layer {importer_layer!r}; "
                "internal packages must be explicitly classified"
            )
            continue

        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), source_file.name)
        except SyntaxError as error:
            violations.append(f"{relative_file}: invalid syntax: {error.msg}")
            continue

        for imported_module in _iter_internal_imports(tree, relative_file):
            target_parts = imported_module.split(".")
            if len(target_parts) < 2:
                violations.append(
                    f"{relative_file}: ambiguous root package import is forbidden; "
                    "import a concrete internal module"
                )
                continue
            target_layer = _target_layer(target_parts[1])
            if target_layer == "*":
                violations.append(
                    f"{relative_file}: star import from {PACKAGE_NAME} is forbidden; "
                    "dependency targets must be explicit"
                )
                continue
            if target_layer not in _ALLOWED_LAYER_DEPENDENCIES:
                violations.append(
                    f"{relative_file}: unknown target layer {target_layer!r}; "
                    "internal packages must be explicitly classified"
                )
                continue
            if target_layer not in _ALLOWED_LAYER_DEPENDENCIES[importer_layer]:
                violations.append(
                    f"{relative_file}: {importer_layer} -> {target_layer} is forbidden; "
                    "target is not present in the explicit allowed dependency matrix"
                )

    return tuple(sorted(set(violations)))


def _iter_internal_imports(
    tree: ast.AST,
    relative_file: Path,
) -> Iterable[str]:
    current_package = _current_package(relative_file)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PACKAGE_NAME or alias.name.startswith(
                    f"{PACKAGE_NAME}."
                ):
                    yield alias.name
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_from(node, current_package)
            if not (
                resolved == PACKAGE_NAME or resolved.startswith(f"{PACKAGE_NAME}.")
            ):
                continue
            if any(alias.name == "*" for alias in node.names):
                yield f"{PACKAGE_NAME}.*"
                continue
            if resolved == PACKAGE_NAME:
                for alias in node.names:
                    yield f"{PACKAGE_NAME}.{alias.name}"
            else:
                yield resolved


def _importer_layer(relative_file: Path) -> str:
    if len(relative_file.parts) == 1:
        if relative_file.name in {"main.py", "__main__.py"}:
            return _APPLICATION_ENTRY_LAYER
        return _ROOT_PACKAGE_LAYER
    return relative_file.parts[0]


def _target_layer(module_name: str) -> str:
    """将正式启动模块归类为独立的应用入口层。"""
    if module_name in {"main", "__main__"}:
        return _APPLICATION_ENTRY_LAYER
    return module_name


def _current_package(relative_file: Path) -> tuple[str, ...]:
    module_parts = relative_file.with_suffix("").parts
    if module_parts[-1] == "__init__":
        return (PACKAGE_NAME, *module_parts[:-1])
    return (PACKAGE_NAME, *module_parts[:-1])


def _resolve_import_from(
    node: ast.ImportFrom,
    current_package: tuple[str, ...],
) -> str:
    if node.level == 0:
        return node.module or ""

    parent_steps = node.level - 1
    if parent_steps >= len(current_package):
        return ""
    base = current_package[: len(current_package) - parent_steps]
    suffix = tuple((node.module or "").split(".")) if node.module else ()
    return ".".join((*base, *suffix))
