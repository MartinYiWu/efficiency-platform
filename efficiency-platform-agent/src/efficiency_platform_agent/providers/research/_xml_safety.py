"""XML/Feed 共用的确定性结构门禁。"""

from __future__ import annotations

from xml.etree.ElementTree import Element

from defusedxml import ElementTree  # type: ignore[import-untyped]


class UnsafeXmlError(ValueError):
    pass


def parse_safe_xml(
    body: bytes, *, max_depth: int = 32, max_nodes: int = 20_000
) -> Element:
    upper = body[:65_536].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise UnsafeXmlError("XML_DECLARATION_FORBIDDEN")
    try:
        root = ElementTree.fromstring(body)
    except Exception as exc:
        raise UnsafeXmlError("XML_INVALID") from exc
    nodes = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if depth > max_depth:
            raise UnsafeXmlError("XML_DEPTH_EXCEEDED")
        if nodes > max_nodes:
            raise UnsafeXmlError("XML_NODE_LIMIT_EXCEEDED")
        stack.extend((child, depth + 1) for child in node)
    return root


__all__ = ["UnsafeXmlError", "parse_safe_xml"]
