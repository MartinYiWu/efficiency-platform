"""工具拥有者可使用的纯 CPU 字段、行选择与不透明回执。"""

from __future__ import annotations

import secrets
from dataclasses import replace

from efficiency_platform_agent.core.context_projection import (
    ProjectionBinding,
    ProjectionPolicy,
    ToolProjection,
    ToolProjectionSource,
    projection_token_upper_bound,
)
from efficiency_platform_agent.core.memory import require_count
from efficiency_platform_agent.core.run import JsonObject


class CursorAuthority:
    """仅由可信代码持有的短期回执表；不是分页授权本身。"""

    def __init__(self) -> None:
        self._receipts: dict[str, tuple[ProjectionBinding, int]] = {}

    def issue(self, binding: ProjectionBinding, *, expires_at_epoch_ms: int) -> str:
        if not isinstance(binding, ProjectionBinding):
            raise TypeError("CURSOR_SCOPE_INVALID")
        require_count(expires_at_epoch_ms)
        receipt = secrets.token_urlsafe(32)
        self._receipts[receipt] = binding, expires_at_epoch_ms
        return receipt

    def validate(
        self, receipt: str, binding: ProjectionBinding, *, now_epoch_ms: int
    ) -> ProjectionBinding:
        require_count(now_epoch_ms)
        stored = self._receipts.get(receipt)
        if stored is None or stored[0] != binding or now_epoch_ms >= stored[1]:
            raise ValueError("CURSOR_SCOPE_OR_EXPIRY_INVALID")
        return stored[0]


def project_tool_source(
    source: ToolProjectionSource,
    policy: ProjectionPolicy,
    *,
    next_cursor: str | None = None,
    cursor_authority: CursorAuthority | None = None,
    now_epoch_ms: int | None = None,
) -> ToolProjection:
    if source.binding != policy.binding:
        raise ValueError("PROJECTION_SCOPE_MISMATCH")
    if not set(source.safety_dependencies).issubset(policy.authorized_dependencies):
        raise ValueError("PROJECTION_SOURCE_NOT_AUTHORIZED")
    if next_cursor is not None:
        if cursor_authority is None or now_epoch_ms is None:
            raise ValueError("CURSOR_VALIDATION_REQUIRED")
        cursor_authority.validate(
            next_cursor, policy.binding, now_epoch_ms=now_epoch_ms
        )
    rows = tuple(
        JsonObject(
            tuple(
                (key, value)
                for key, value in row.data.items
                if key in policy.allowed_fields
            )
        )
        for row in source.rows[: policy.max_rows]
    )
    truncated = source.truncated or len(rows) < len(source.rows)
    reason = (
        "RESULT_LIMIT" if len(rows) < len(source.rows) else source.truncation_reason
    )
    completeness = source.completeness
    if completeness == "COMPLETE" and (truncated or next_cursor is not None):
        completeness = "PARTIAL"
    view = ToolProjection(
        source.binding,
        rows,
        completeness,
        source.total_count,
        len(rows),
        truncated,
        reason,
        next_cursor,
        policy.projection_schema,
        policy.projection_version,
        source.safety_dependencies,
        source.retention_ref,
        policy.model_visible_token_upper_bound,
    )
    while projection_token_upper_bound(view) > policy.model_visible_token_upper_bound:
        if not view.data:
            raise ValueError("PROJECTION_ENVELOPE_TOO_LARGE")
        view = replace(
            view,
            data=view.data[:-1],
            returned_count=view.returned_count - 1,
            completeness="UNKNOWN" if completeness == "UNKNOWN" else "PARTIAL",
            truncated=True,
            truncation_reason="TOKEN_LIMIT",
        )
    return view
