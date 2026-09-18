"""确定性校验与派生 Deliverable V2 的用户展示结果。"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit

from efficiency_platform_agent.contracts.deliverables import (
    CitationV1,
    DeliverableSetV1,
    DeliverableSetV2,
    DeliverableV1,
    OperationDeliverableV2,
    WarningV2,
)

_ALLOWED_ACTION_TYPES = {
    "rewrite_for_platform",
    "expand_item",
    "generate_script",
    "replace_candidates",
    "show_sources",
    "refine_constraints",
}

_PRIORITY_LABELS = {
    "high": "高优先级",
    "medium": "中优先级",
    "low": "低优先级",
}

_NON_VISIBLE_DELIVERY_FIELDS = frozenset(
    {
        "action_id",
        "candidate_count",
        "citation_id",
        "collection_window_end",
        "collection_window_start",
        "complete",
        "confidence",
        "contract_version",
        "degraded",
        "deliverable_id",
        "eliminated_count",
        "finding_id",
        "independent_source_group",
        "intent_patch",
        "intent_revision",
        "item_id",
        "merged_event_count",
        "occurred_at",
        "phase_id",
        "published_at",
        "ranking_basis",
        "requires_user_input",
        "result_count",
        "retained_count",
        "run_id",
        "source_count",
        "source_refs",
        "source_tier",
        "source_type",
        "supports_item_ids",
        "target_deliverable_id",
        "target_item_ids",
        "url",
        "verified_source_count",
        "verification_status",
    }
)

_FORBIDDEN_VISIBLE_CONTENT = (
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"hidden\s+reasoning", re.IGNORECASE),
)


class DeliveryPresentationValidator:
    """校验交付物展示不变量并重算复制文本。"""

    def validate_deliverable(
        self, value: OperationDeliverableV2
    ) -> OperationDeliverableV2:
        """验证排名与引用闭包，并返回确定性复制文本快照。"""

        if value.content.kind == "ranked_digest":
            citations = {citation.citation_id for citation in value.citations}
            referenced = {
                reference
                for item in value.content.items
                for reference in item.source_refs
            }
            if not referenced.issubset(citations):
                raise ValueError("DELIVERY_CITATION_CLOSURE_INVALID")

            ranks = [item.rank for item in value.content.items]
            if ranks != list(range(1, len(ranks) + 1)):
                raise ValueError("DELIVERY_RANK_INVALID")

        _validate_citation_urls(value)
        rendered = render_copy_text(value)
        validated = value.model_copy(update={"copy_text": rendered})
        _validate_visible_content(validated.model_dump(mode="json"))
        return validated


def render_copy_text(value: OperationDeliverableV2) -> str:
    """按五类结构化内容生成固定顺序的纯文本，不调用模型。"""

    content = value.content
    if content.kind == "ranked_digest":
        blocks: list[str] = []
        for item in content.items:
            lines = [
                f"{item.rank}. {item.title}",
                f"摘要：{item.summary}",
                f"运营价值：{item.why_it_matters}",
            ]
            if item.content_angles:
                lines.append(f"内容角度：{'、'.join(item.content_angles)}")
            if item.metrics:
                lines.append(f"指标：{'、'.join(item.metrics)}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    if content.kind == "platform_content":
        sections = [content.body_markdown.rstrip()]
        if content.hashtags:
            sections.append(" ".join(content.hashtags))
        return "\n\n".join(sections)

    if content.kind == "action_plan":
        sections = [f"目标：{content.goal}\n受众：{content.audience}"]
        for phase_index, phase in enumerate(content.phases, start=1):
            phase_lines = [f"阶段 {phase_index}：{phase.title}"]
            phase_lines.extend(
                f"{action_index}. {action}"
                for action_index, action in enumerate(phase.actions, start=1)
            )
            if phase.metrics:
                phase_lines.append(f"阶段指标：{'、'.join(phase.metrics)}")
            sections.append("\n".join(phase_lines))
        trailing: list[str] = []
        if content.metrics:
            trailing.append(f"整体指标：{'、'.join(content.metrics)}")
        if content.assumptions:
            trailing.append(f"假设：{'、'.join(content.assumptions)}")
        if trailing:
            sections.append("\n".join(trailing))
        return "\n\n".join(sections)

    if content.kind == "diagnosis":
        blocks = []
        for finding_index, finding in enumerate(content.findings, start=1):
            lines = [
                (
                    f"{finding_index}. [{_PRIORITY_LABELS[finding.priority]}] "
                    f"{finding.title}"
                )
            ]
            if finding.evidence:
                lines.append(f"证据：{'、'.join(finding.evidence)}")
            lines.append(f"建议：{finding.recommendation}")
            blocks.append("\n".join(lines))
        if content.data_gaps:
            blocks.append(f"数据缺口：{'、'.join(content.data_gaps)}")
        return "\n\n".join(blocks)

    retrospective_sections = (
        ("目标", content.objectives),
        ("结果", content.outcomes),
        ("差距", content.gaps),
        ("原因", content.causes),
        ("下一步", content.next_steps),
    )
    return "\n\n".join(
        f"{title}\n{_render_numbered(values)}"
        for title, values in retrospective_sections
    )


def assemble_set_v2(value: DeliverableSetV2) -> DeliverableSetV2:
    """校验集合级引用、目标和独立性，并生成确定性展示字段。"""

    deliverable_ids = [item.deliverable_id for item in value.deliverables]
    if len(deliverable_ids) != len(set(deliverable_ids)):
        raise ValueError("DELIVERY_ID_DUPLICATED")

    validator = DeliveryPresentationValidator()
    deliverables = [validator.validate_deliverable(item) for item in value.deliverables]
    _validate_visible_content(
        value.model_copy(update={"deliverables": deliverables}).model_dump(mode="json")
    )

    if any(item.content.kind == "ranked_digest" for item in deliverables):
        provenance = value.provenance
        if (
            provenance is None
            or provenance.collection_window_start is None
            or provenance.collection_window_end is None
            or provenance.ranking_basis is None
        ):
            raise ValueError("DELIVERY_RESEARCH_PROVENANCE_REQUIRED")

    _validate_platform_content_independence(deliverables)
    _validate_next_actions(value, deliverables)

    warnings = _deduplicate_warnings(value.warnings)
    degraded = (
        value.degraded
        or not value.summary.complete
        or bool(warnings)
        or any(item.warnings for item in deliverables)
    )
    return value.model_copy(
        update={
            "deliverables": deliverables,
            "degraded": degraded,
            "warnings": warnings,
        }
    )


def project_set_v2_to_v1(value: DeliverableSetV2) -> DeliverableSetV1:
    """只投影 V1 明确拥有的字段，不反推 V2 质量语义。"""

    deliverables = []
    for item in value.deliverables:
        platform_content = (
            item.content if item.content.kind == "platform_content" else None
        )
        deliverables.append(
            DeliverableV1(
                platform=item.platform,
                title=item.title,
                body=item.copy_text,
                hashtags=(platform_content.hashtags if platform_content else []),
                format_notes=(
                    platform_content.format_notes if platform_content else []
                ),
                citations=[
                    CitationV1(
                        url=citation.url, title=citation.title, source=citation.source
                    )
                    for citation in item.citations
                ],
                warnings=[warning.code for warning in item.warnings],
            )
        )
    return DeliverableSetV1(
        deliverables=deliverables,
        summary=value.summary.message,
        degraded=value.degraded,
    )


def _render_numbered(values: list[str]) -> str:
    """用从一开始的稳定编号渲染字符串列表。"""

    if not values:
        return "无"
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def _validate_platform_content_independence(
    deliverables: list[OperationDeliverableV2],
) -> None:
    """拒绝不同平台间标准化后完全相同的正文。"""

    platform_by_digest: dict[str, str] = {}
    for item in deliverables:
        if item.content.kind != "platform_content":
            continue
        normalized = "".join(
            unicodedata.normalize("NFKC", item.content.body_markdown).split()
        )
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        previous_platform = platform_by_digest.get(digest)
        if previous_platform is not None and previous_platform != item.platform:
            raise ValueError("DELIVERY_PLATFORM_CONTENT_DUPLICATED")
        platform_by_digest[digest] = item.platform


def _validate_next_actions(
    value: DeliverableSetV2,
    deliverables: list[OperationDeliverableV2],
) -> None:
    """校验允许动作、交付物目标与排名条目目标。"""

    deliverable_by_id = {item.deliverable_id: item for item in deliverables}
    for action in value.next_actions:
        if action.action_type not in _ALLOWED_ACTION_TYPES:
            raise ValueError("DELIVERY_ACTION_TYPE_INVALID")
        target = (
            deliverable_by_id.get(action.target_deliverable_id)
            if action.target_deliverable_id is not None
            else None
        )
        if action.target_deliverable_id is not None and target is None:
            raise ValueError("DELIVERY_ACTION_TARGET_INVALID")
        if not action.target_item_ids:
            continue
        if target is None or target.content.kind != "ranked_digest":
            raise ValueError("DELIVERY_ACTION_ITEM_TARGET_INVALID")
        item_ids = {item.item_id for item in target.content.items}
        if not set(action.target_item_ids).issubset(item_ids):
            raise ValueError("DELIVERY_ACTION_ITEM_TARGET_INVALID")


def _validate_citation_urls(value: OperationDeliverableV2) -> None:
    """拒绝不能安全呈现为外链的来源地址。"""

    for citation in value.citations:
        url = citation.url
        if not url or any(character.isspace() for character in url):
            raise ValueError("DELIVERY_CITATION_INVALID")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
        except ValueError as error:
            raise ValueError("DELIVERY_CITATION_INVALID") from error
        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("DELIVERY_CITATION_INVALID")


def _validate_visible_content(value: Any, *, field_name: str | None = None) -> None:
    """递归检查公开展示文本，不检查下一轮内部意图补丁。"""

    if isinstance(value, str):
        if field_name not in _NON_VISIBLE_DELIVERY_FIELDS:
            normalized = unicodedata.normalize("NFKC", value)
            if any(
                pattern.search(normalized) for pattern in _FORBIDDEN_VISIBLE_CONTENT
            ):
                raise ValueError("DELIVERY_INTERNAL_CONTENT_FORBIDDEN")
        return
    if isinstance(value, list):
        for item in value:
            _validate_visible_content(item, field_name=field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _NON_VISIBLE_DELIVERY_FIELDS:
                continue
            _validate_visible_content(item, field_name=key)


def _deduplicate_warnings(warnings: list[WarningV2]) -> list[WarningV2]:
    """按首次出现顺序移除完全重复的结构化提醒。"""

    result: list[WarningV2] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code, warning.message)
        if key not in seen:
            seen.add(key)
            result.append(warning)
    return result


__all__ = [
    "DeliveryPresentationValidator",
    "assemble_set_v2",
    "project_set_v2_to_v1",
    "render_copy_text",
]
