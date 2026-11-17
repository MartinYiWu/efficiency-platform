"""上下文投影的中立、不可变合同；授权由可信拥有者提供。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol

from .memory import (
    ExecutionScope,
    SourceDependency,
    require_bool,
    require_count,
    require_dependencies,
    require_id,
    require_ids,
)
from .run import JsonObject, JsonValue, ToolRequest, ToolResult


@dataclass(frozen=True, slots=True)
class ProjectionBinding:
    scope: ExecutionScope
    query_scope_ref: str
    snapshot_ref: str
    snapshot_version: str
    query_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("PROJECTION_SCOPE_INVALID")
        for value in (
            self.query_scope_ref,
            self.snapshot_ref,
            self.snapshot_version,
            self.query_ref,
        ):
            require_id(value)


def tool_query_ref(request: ToolRequest) -> str:
    """绑定工具名、版本和完整不可变参数；摘要本身不授予查询权限。"""
    payload = repr((request.tool_name, request.contract_version, request.arguments))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectionPolicy:
    binding: ProjectionBinding
    projection_schema: str
    projection_version: str
    allowed_fields: frozenset[str]
    max_rows: int
    model_visible_token_upper_bound: int
    authorized_dependencies: tuple[SourceDependency, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProjectionBinding):
            raise TypeError("PROJECTION_SCOPE_INVALID")
        require_id(self.projection_schema)
        require_id(self.projection_version)
        require_ids(self.allowed_fields)
        require_count(self.max_rows)
        require_count(self.model_visible_token_upper_bound)
        require_dependencies(self.authorized_dependencies)


@dataclass(frozen=True, slots=True)
class ScopedProjectionRow:
    binding: ProjectionBinding
    data: JsonObject = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProjectionBinding) or not isinstance(
            self.data, JsonObject
        ):
            raise TypeError("PROJECTION_ROW_INVALID")


@dataclass(frozen=True, slots=True)
class ToolProjectionSource:
    binding: ProjectionBinding
    rows: tuple[ScopedProjectionRow, ...] = field(repr=False)
    completeness: str
    total_count: int | None
    total_binding: ProjectionBinding | None
    safety_dependencies: tuple[SourceDependency, ...]
    retention_ref: str
    truncated: bool = False
    truncation_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProjectionBinding):
            raise TypeError("PROJECTION_SCOPE_INVALID")
        if type(self.rows) is not tuple or any(
            not isinstance(row, ScopedProjectionRow) for row in self.rows
        ):
            raise TypeError("PROJECTION_ROWS_INVALID")
        validate_completeness(self.completeness)
        require_dependencies(self.safety_dependencies)
        require_id(self.retention_ref)
        require_bool(self.truncated)
        validate_truncation(self.truncated, self.truncation_reason)
        if self.total_count is not None:
            require_count(self.total_count)
            if self.total_binding != self.binding:
                raise ValueError("PROJECTION_TOTAL_SCOPE_MISMATCH")
            if self.total_count < len(self.rows):
                raise ValueError("PROJECTION_COUNT_INVALID")
        elif self.total_binding is not None:
            raise ValueError("PROJECTION_TOTAL_SCOPE_MISMATCH")
        if any(row.binding != self.binding for row in self.rows):
            raise ValueError("PROJECTION_ROW_SCOPE_MISMATCH")
        if self.completeness == "COMPLETE" and (
            self.truncated
            or (self.total_count is not None and self.total_count != len(self.rows))
        ):
            raise ValueError("PROJECTION_COMPLETENESS_INVALID")


def validate_completeness(value: str) -> None:
    if value not in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
        raise ValueError("PROJECTION_COMPLETENESS_INVALID")


def validate_truncation(truncated: bool, reason: str | None) -> None:
    if reason not in {
        None,
        "TOKEN_LIMIT",
        "RESULT_LIMIT",
        "FIELD_PROJECTION",
        "SOURCE_LIMIT",
    }:
        raise ValueError("PROJECTION_TRUNCATION_INVALID")
    if truncated != (reason is not None):
        raise ValueError("PROJECTION_TRUNCATION_INVALID")


@dataclass(frozen=True, slots=True)
class ToolProjection:
    binding: ProjectionBinding
    data: tuple[JsonObject, ...] = field(repr=False)
    completeness: str
    total_count: int | None
    returned_count: int
    truncated: bool
    truncation_reason: str | None
    next_cursor: str | None
    projection_schema: str
    projection_version: str
    safety_dependencies: tuple[SourceDependency, ...]
    retention_ref: str
    model_visible_token_upper_bound: int

    def __post_init__(self) -> None:
        if not isinstance(self.binding, ProjectionBinding):
            raise TypeError("PROJECTION_SCOPE_INVALID")
        if type(self.data) is not tuple or any(
            not isinstance(row, JsonObject) for row in self.data
        ):
            raise TypeError("PROJECTION_DATA_INVALID")
        validate_completeness(self.completeness)
        require_count(self.returned_count)
        require_count(self.model_visible_token_upper_bound)
        require_bool(self.truncated)
        validate_truncation(self.truncated, self.truncation_reason)
        if len(self.data) != self.returned_count:
            raise ValueError("PROJECTION_COUNT_INVALID")
        if self.total_count is not None:
            require_count(self.total_count)
            if self.returned_count > self.total_count:
                raise ValueError("PROJECTION_COUNT_INVALID")
        if self.completeness == "COMPLETE" and (
            self.truncated
            or self.next_cursor is not None
            or (
                self.total_count is not None and self.returned_count != self.total_count
            )
        ):
            raise ValueError("PROJECTION_COMPLETENESS_INVALID")
        for value in (
            self.projection_schema,
            self.projection_version,
            self.retention_ref,
        ):
            require_id(value)
        if self.next_cursor is not None:
            require_id(self.next_cursor)
        require_dependencies(self.safety_dependencies)

    @property
    def source_dependencies(self) -> tuple[SourceDependency, ...]:
        return self.safety_dependencies

    def to_json(self) -> JsonObject:
        return JsonObject(
            (
                ("data", self.data),
                ("completeness", self.completeness),
                ("total_count", self.total_count),
                ("returned_count", self.returned_count),
                ("truncated", self.truncated),
                ("truncation_reason", self.truncation_reason),
                ("next_cursor", self.next_cursor),
                ("snapshot_ref", self.binding.snapshot_ref),
                ("snapshot_version", self.binding.snapshot_version),
                ("projection_schema", self.projection_schema),
                ("projection_version", self.projection_version),
                ("query_scope_ref", self.binding.query_scope_ref),
                (
                    "safety_dependencies",
                    tuple(dependency_json(item) for item in self.safety_dependencies),
                ),
            )
        )


def dependency_json(item: SourceDependency) -> JsonObject:
    return JsonObject(
        (
            ("source_type", item.source_type),
            ("source_id", item.source_id),
            ("source_version", item.source_version),
            ("grant_epoch", item.grant_epoch),
            ("source_epoch", item.source_epoch),
            ("deletion_epoch", item.deletion_epoch),
        )
    )


def scope_json(scope: ExecutionScope) -> JsonObject:
    conversation = scope.conversation
    return JsonObject(
        (
            ("tenant_id", conversation.tenant_id),
            ("principal_id", conversation.user_id),
            ("domain", conversation.domain),
            ("top_level_agent_id", conversation.top_level_agent_id),
            ("session_kind", conversation.session_kind),
            ("session_id", conversation.session_id),
            ("task_id", scope.task_id),
            ("execution_id", scope.execution_id),
            ("subtask_id", scope.subtask_id),
            ("purpose", scope.purpose),
            ("execution_agent_id", scope.execution_agent_id),
        )
    )


class ToolProjectionPort(Protocol):
    """工具拥有者提供授权后的程序投影；不得再次调用模型。"""

    def project(
        self, request: ToolRequest, result: ToolResult, selection: ProjectionPolicy
    ) -> ToolProjection: ...


def _projection_plain(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _projection_plain(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_projection_plain(item) for item in value]
    return value


def projection_token_upper_bound(view: ToolProjection) -> int:
    """UTF8 字节加消息封装余量；完整 Provider 请求仍须独立计数。"""
    return (
        len(
            json.dumps(
                _projection_plain(view.to_json()),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        + 256
    )


@dataclass(frozen=True, slots=True)
class SpecialistContextSlice:
    """可信 Supervisor 创建的最小子任务上下文；不包含父历史。"""

    contract_version: str
    scope: ExecutionScope
    goal: str = field(repr=False)
    constraints: tuple[str, ...] = field(repr=False)
    source_dependencies: tuple[SourceDependency, ...]
    preferences: tuple[str, ...] = field(repr=False)
    allowed_tools: frozenset[str]
    output_contract: str
    window_policy_ref: str
    parent_budget_ref: str
    requested_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.contract_version != "specialist-context-slice/1":
            raise ValueError("CONTEXT_SLICE_VERSION_INVALID")
        if not isinstance(self.scope, ExecutionScope):
            raise TypeError("CONTEXT_SLICE_SCOPE_INVALID")
        for value in (
            self.output_contract,
            self.window_policy_ref,
            self.parent_budget_ref,
        ):
            require_id(value)
        if type(self.goal) is not str or not self.goal.strip():
            raise ValueError("CONTEXT_SLICE_GOAL_INVALID")
        for values in (self.constraints, self.preferences, self.requested_scope):
            if type(values) is not tuple or any(
                type(value) is not str or not value.strip() for value in values
            ):
                raise ValueError("CONTEXT_SLICE_FIELDS_INVALID")
        if not self.requested_scope or len(set(self.requested_scope)) != len(
            self.requested_scope
        ):
            raise ValueError("CONTEXT_SLICE_COVERAGE_INVALID")
        require_dependencies(self.source_dependencies)
        require_ids(self.allowed_tools)

    def to_json(self) -> JsonObject:
        return JsonObject(
            (
                ("contract_version", self.contract_version),
                ("scope", scope_json(self.scope)),
                ("goal", self.goal),
                ("constraints", self.constraints),
                (
                    "source_dependencies",
                    tuple(dependency_json(item) for item in self.source_dependencies),
                ),
                ("preferences", self.preferences),
                ("allowed_tools", tuple(sorted(self.allowed_tools))),
                ("output_contract", self.output_contract),
                ("window_policy_ref", self.window_policy_ref),
                ("parent_budget_ref", self.parent_budget_ref),
                ("requested_scope", self.requested_scope),
            )
        )


@dataclass(frozen=True, slots=True)
class SpecialistResultProjection:
    """子任务结论只代表显式覆盖范围；展示引用不能削弱安全依赖。"""

    contract_version: str
    task_id: str
    scope: ExecutionScope
    conclusions: tuple[str, ...] = field(repr=False)
    evidence_refs: tuple[str, ...]
    unresolved_questions: tuple[str, ...] = field(repr=False)
    risks: tuple[str, ...] = field(repr=False)
    recommendations: tuple[tuple[str, str], ...] = field(repr=False)
    artifact_refs: tuple[str, ...]
    completeness: str
    completed_scope: tuple[str, ...]
    missing_scope: tuple[str, ...]
    source_dependencies: tuple[SourceDependency, ...]
    safety_dependencies: tuple[SourceDependency, ...]

    def __post_init__(self) -> None:
        if self.contract_version != "specialist-result-projection/1":
            raise ValueError("RESULT_PROJECTION_VERSION_INVALID")
        require_id(self.task_id)
        if (
            not isinstance(self.scope, ExecutionScope)
            or self.scope.subtask_id != self.task_id
        ):
            raise ValueError("RESULT_PROJECTION_SCOPE_INVALID")
        validate_completeness(self.completeness)
        for values in (
            self.conclusions,
            self.evidence_refs,
            self.unresolved_questions,
            self.risks,
            self.artifact_refs,
            self.completed_scope,
            self.missing_scope,
        ):
            if type(values) is not tuple or any(
                type(value) is not str or not value.strip() for value in values
            ):
                raise ValueError("RESULT_PROJECTION_FIELDS_INVALID")
        if type(self.recommendations) is not tuple:
            raise TypeError("RESULT_PROJECTION_RECOMMENDATIONS_INVALID")
        for item in self.recommendations:
            if (
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or not item[0].strip()
                or item[1] not in {"PROPOSED", "ACCEPTED", "REJECTED", "UNRESOLVED"}
            ):
                raise ValueError("RESULT_PROJECTION_RECOMMENDATIONS_INVALID")
        if set(self.completed_scope).intersection(self.missing_scope):
            raise ValueError("RESULT_PROJECTION_COVERAGE_INVALID")
        if self.completeness == "COMPLETE" and self.missing_scope:
            raise ValueError("RESULT_PROJECTION_COVERAGE_INVALID")
        if self.completeness != "COMPLETE" and not self.missing_scope:
            raise ValueError("RESULT_PROJECTION_COVERAGE_INVALID")
        require_dependencies(self.source_dependencies)
        require_dependencies(self.safety_dependencies)
        if not set(self.source_dependencies).issubset(self.safety_dependencies):
            raise ValueError("RESULT_PROJECTION_DEPENDENCIES_INCOMPLETE")

    def validate_slice(self, slice_: SpecialistContextSlice) -> None:
        if (
            self.scope != slice_.scope
            or set(self.completed_scope).union(self.missing_scope)
            != set(slice_.requested_scope)
            or set(self.safety_dependencies) != set(slice_.source_dependencies)
        ):
            raise ValueError("RESULT_PROJECTION_SLICE_MISMATCH")

    def to_json(self) -> JsonObject:
        return JsonObject(
            (
                ("contract_version", self.contract_version),
                ("task_id", self.task_id),
                ("scope", scope_json(self.scope)),
                ("conclusions", self.conclusions),
                ("evidence_refs", self.evidence_refs),
                ("unresolved_questions", self.unresolved_questions),
                ("risks", self.risks),
                ("recommendations", self.recommendations),
                ("artifact_refs", self.artifact_refs),
                ("completeness", self.completeness),
                ("completed_scope", self.completed_scope),
                ("missing_scope", self.missing_scope),
                (
                    "source_dependencies",
                    tuple(dependency_json(item) for item in self.source_dependencies),
                ),
                (
                    "safety_dependencies",
                    tuple(dependency_json(item) for item in self.safety_dependencies),
                ),
            )
        )
