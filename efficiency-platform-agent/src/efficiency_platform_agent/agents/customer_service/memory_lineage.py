"""Java原目录与Agent拥有的PG member/file SHA严格对齐；不回调Java查询权限。"""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from efficiency_platform_agent.core.memory import SourceDependency
from efficiency_platform_agent.core.run_context_binding import current_run_context


def directory() -> dict[tuple[str, ...], tuple[str, SourceDependency]] | None:
    binding = current_run_context()
    if binding is None or binding.memory_context is None:
        return None
    context = binding.memory_context
    if context.knowledge_context_json is None:
        return None
    data = json.loads(context.knowledge_context_json)
    if (
        set(data) != {"schema_version", "tenant_id", "user_id", "documents"}
        or data["schema_version"] != "knowledge-context/1"
        or (data["tenant_id"], data["user_id"])
        != (binding.conversation.tenant_id, binding.conversation.user_id)
    ):
        raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_INVALID")
    documents = data["documents"]
    if not isinstance(documents, list) or not 1 <= len(documents) <= 128:
        raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_INVALID")
    result = {}
    for document in documents:
        if set(document) != {
            "knowledge_base_id",
            "index_release_id",
            "document_id",
            "document_version_id",
            "file_sha256",
            "source",
        }:
            raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_INVALID")
        source = SourceDependency(**document["source"])
        if (
            source.source_type != "KNOWLEDGE_DOCUMENT"
            or source not in context.packet.safety_dependencies
        ):
            raise ValueError("MEMORY_KNOWLEDGE_SOURCE_DENIED")
        key = tuple(
            document[field]
            for field in (
                "knowledge_base_id",
                "index_release_id",
                "document_id",
                "document_version_id",
            )
        )
        version = hashlib.sha256(
            json.dumps(
                [*key, document["file_sha256"]],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if source.source_version != version:
            raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_INVALID")
        if key in result or len(document["file_sha256"]) != 64:
            raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_INVALID")
        result[key] = (document["file_sha256"], source)
    return result


def validate_evidence(items: tuple[Any, ...]) -> tuple[SourceDependency, ...]:
    catalog = directory()
    if catalog is None:
        binding = current_run_context()
        if binding is not None and binding.memory_context is not None:
            raise ValueError("MEMORY_KNOWLEDGE_DIRECTORY_REQUIRED")
        return ()
    dependencies = []
    for item in items:
        key = tuple(
            str(getattr(item, field))
            for field in (
                "knowledge_base_id",
                "index_release_id",
                "document_id",
                "document_version_id",
            )
        )
        allowed = catalog.get(key)
        if (
            allowed is None
            or getattr(item, "document_sha256", None) != allowed[0]
            or hashlib.sha256(item.content.encode()).hexdigest() != item.content_hash
        ):
            raise ValueError("MEMORY_KNOWLEDGE_EVIDENCE_MISMATCH")
        dependencies.append(allowed[1])
    return tuple(dict.fromkeys(dependencies))


def stage_dependencies(
    value: object, seen: set[SourceDependency]
) -> tuple[SourceDependency, ...]:
    binding = current_run_context()
    if binding is None or binding.memory_context is None:
        return ()
    catalog = directory()
    if catalog is None:
        return binding.memory_context.input_dependencies

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            if "document_version_id" in item:
                names = (
                    "knowledge_base_id",
                    "index_release_id",
                    "document_id",
                    "document_version_id",
                )
                if any(name not in item for name in names):
                    raise ValueError("MEMORY_KNOWLEDGE_EVIDENCE_MISMATCH")
                key = tuple(str(item[name]) for name in names)
                allowed = catalog.get(key)
                if allowed is None or item.get("document_sha256") != allowed[0]:
                    raise ValueError("MEMORY_KNOWLEDGE_EVIDENCE_MISMATCH")
                seen.add(allowed[1])
            for child in item.values():
                visit(child)
        elif isinstance(item, (tuple, list)):
            for child in item:
                visit(child)

    visit(value)
    # 已见证据衍生出的充分性/冲突/修复也继承真实上游输入，不能按展示引用缩小。
    return tuple(
        dict.fromkeys(
            (
                *binding.memory_context.input_dependencies,
                *sorted(seen, key=lambda dep: (dep.source_type, dep.source_id)),
            )
        )
    )
