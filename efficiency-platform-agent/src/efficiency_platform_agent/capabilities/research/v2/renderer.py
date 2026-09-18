"""只从结构化交付包生成安全 Markdown。"""

from __future__ import annotations

import html
from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.research_v2 import DeliveryPackV2


def render_markdown(pack: DeliveryPackV2) -> str:
    if not isinstance(pack, DeliveryPackV2):
        raise TypeError("pack 必须为 DeliveryPackV2")
    lines = ["# 研究结果", "", _escape(pack.content)]
    for index, event in enumerate(pack.events, 1):
        lines.extend(["", f"## {index}. {_escape(event.title)}"])
        if event.event_time is not None:
            lines.append(f"时间：{event.event_time.isoformat()}")
        for claim in event.claim_texts:
            lines.append(f"- {_escape(claim)}")
        lines.append("来源：")
        for citation in event.citations:
            label = _escape(f"{citation.publisher_id}｜{citation.title}")
            parsed = urlsplit(citation.url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("DELIVERY_CITATION_URL_INVALID")
            url = citation.url.replace("(", "%28").replace(")", "%29")
            lines.append(
                f"- [{label}]({url})（{citation.source_role}，证据 {citation.evidence_id}）"
            )
            if citation.content_scope is not None:
                scope = {
                    "summary": "摘要",
                    "full": "全文",
                    "platform_text": "平台正文",
                }[citation.content_scope]
                checked = (
                    "已核验摘录与来源正文一致"
                    if citation.verification_status == "verified"
                    else "未核验"
                )
                lines.append(f"  内容范围：{scope}；{checked}。")
    if pack.limitations:
        lines.extend(
            ["", "## 局限", *[f"- {_escape(item)}" for item in pack.limitations]]
        )
    return "\n".join(lines)


def _escape(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("`", "&#96;")
    return "".join(f"\\{char}" if char in "[]()" else char for char in escaped)


__all__ = ["render_markdown"]
