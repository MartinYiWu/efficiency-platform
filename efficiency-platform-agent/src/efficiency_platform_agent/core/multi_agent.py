"""受控多 Agent 编排所需的框架中立核心值对象。

本模块只依赖标准库和 ``core`` 既有契约，不包含调度、模型调用、持久化或
编排框架实现。所有值对象都采用冻结数据类，供 Supervisor、调度器和状态
适配层共享。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from .agent import CapabilityRequirement
from .run import ExecutionBudget, JsonObject, SupervisorTask

_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_PLATFORM_LIMITS = {
    "max_delegation_depth": 1,
    "max_dag_depth": 8,
    "max_task_count": 16,
    "max_parallel_tasks": 4,
    "max_plan_revisions": 2,
    "max_task_revisions": 2,
}


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")


def _stable_id(name: str, value: str) -> None:
    if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} 必须是稳定小写标识")


def _non_negative(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} 必须是非负整数")


def _positive(name: str, value: int) -> None:
    _non_negative(name, value)
    if value == 0:
        raise ValueError(f"{name} 必须是正整数")


def _immutable_ids(
    name: str,
    value: Sequence[str],
    *,
    allow_empty: bool = True,
) -> None:
    """校验要求为 tuple 的稳定标识序列。"""
    if not isinstance(value, tuple):
        raise TypeError(f"{name} 必须是不可变 tuple")
    if not allow_empty and not value:
        raise ValueError(f"{name} 不能为空")
    for item in value:
        _stable_id(name, item)


def _immutable_string_set(name: str, value: frozenset[str]) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{name} 必须是不可变 frozenset")
    for item in value:
        _stable_id(name, item)


class TaskExecutionStatus(StrEnum):
    """单个 Specialist 任务的生命周期状态。"""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskFailureMode(StrEnum):
    """单个任务失败后的受控动作。"""

    FAIL_PLAN = "fail_plan"
    WAIT_INPUT = "wait_input"
    RETRY_ONCE = "retry_once"
    SKIP_WITH_WARNING = "skip_with_warning"


class CompletionStatus(StrEnum):
    """Supervisor 对整次运营任务的聚合结果。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    WAITING_INPUT = "waiting_input"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SupervisorLimits:
    """平台级硬上限；场景只能收紧，不能放大。"""

    max_delegation_depth: int = 1
    max_dag_depth: int = 8
    max_task_count: int = 16
    max_parallel_tasks: int = 4
    max_plan_revisions: int = 2
    max_task_revisions: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_delegation_depth",
            "max_dag_depth",
            "max_task_count",
            "max_parallel_tasks",
            "max_plan_revisions",
            "max_task_revisions",
        ):
            _positive(name, getattr(self, name))
        for name, platform_value in _PLATFORM_LIMITS.items():
            if getattr(self, name) > platform_value:
                raise ValueError(f"{name} 不得超过平台硬上限")

    def restrict(self, **requested: int) -> SupervisorLimits:
        """返回收紧后的新上限；任何非法放大或未知字段都失败关闭。"""
        allowed = {
            "max_delegation_depth",
            "max_dag_depth",
            "max_task_count",
            "max_parallel_tasks",
            "max_plan_revisions",
            "max_task_revisions",
        }
        unknown = set(requested).difference(allowed)
        if unknown:
            raise ValueError(f"未知上限字段: {sorted(unknown)}")
        values = {}
        for name in allowed:
            current = getattr(self, name)
            if name not in requested:
                values[name] = current
                continue
            value = requested[name]
            _positive(name, value)
            if value > current:
                raise ValueError(f"{name} 不得放大")
            values[name] = value
        return replace(self, **values)


@dataclass(frozen=True, slots=True)
class TaskNode:
    """从 S3 计划编译而来的单个不可变任务节点。"""

    task_id: str
    task_type: str
    capability_requirement: CapabilityRequirement
    input_schema_version: str
    output_schema_version: str
    depends_on: Sequence[str]
    required: bool
    failure_mode: TaskFailureMode
    input_reference_ids: Sequence[str]
    context_view: JsonObject
    allowed_tools: frozenset[str]
    required_permissions: frozenset[str]
    requested_budget: ExecutionBudget
    expected_deliverable_ids: Sequence[str]
    quality_check_ids: frozenset[str]

    def __post_init__(self) -> None:
        _stable_id("task_id", self.task_id)
        _stable_id("task_type", self.task_type)
        if not isinstance(self.capability_requirement, CapabilityRequirement):
            raise TypeError("capability_requirement 类型无效")
        _text("input_schema_version", self.input_schema_version)
        _text("output_schema_version", self.output_schema_version)
        _immutable_ids("depends_on", self.depends_on)
        if self.task_id in self.depends_on:
            raise ValueError("任务不得依赖自身")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("任务依赖不得重复")
        if not isinstance(self.required, bool):
            raise TypeError("required 必须是 bool")
        if not isinstance(self.failure_mode, TaskFailureMode):
            raise TypeError("failure_mode 必须是 TaskFailureMode")
        if (
            not self.required
            and self.failure_mode is not TaskFailureMode.SKIP_WITH_WARNING
        ):
            raise ValueError("可选任务只能使用告警跳过")
        if self.required and self.failure_mode is TaskFailureMode.SKIP_WITH_WARNING:
            raise ValueError("必需任务不得使用告警跳过")
        _immutable_ids("input_reference_ids", self.input_reference_ids)
        if not isinstance(self.context_view, JsonObject):
            raise TypeError("context_view 必须是 JsonObject")
        _immutable_string_set("allowed_tools", self.allowed_tools)
        _immutable_string_set("required_permissions", self.required_permissions)
        if not isinstance(self.requested_budget, ExecutionBudget):
            raise TypeError("requested_budget 必须是 ExecutionBudget")
        _immutable_ids("expected_deliverable_ids", self.expected_deliverable_ids)
        _immutable_string_set("quality_check_ids", self.quality_check_ids)


@dataclass(frozen=True, slots=True)
class TaskGraph:
    """计划编译后的稳定 DAG 快照。"""

    plan_id: str
    plan_contract_version: str
    plan_revision: int
    tasks: Sequence[TaskNode]
    topological_order: Sequence[str]

    def __post_init__(self) -> None:
        _stable_id("plan_id", self.plan_id)
        _text("plan_contract_version", self.plan_contract_version)
        _non_negative("plan_revision", self.plan_revision)
        if self.plan_revision > SupervisorLimits().max_plan_revisions:
            raise ValueError("计划修订次数超过平台上限")
        if not isinstance(self.tasks, tuple):
            raise TypeError("tasks 必须是不可变 tuple")
        if not self.tasks:
            raise ValueError("任务图不能为空")
        if len(self.tasks) > SupervisorLimits().max_task_count:
            raise ValueError("任务数超过平台上限")
        if any(not isinstance(task, TaskNode) for task in self.tasks):
            raise TypeError("tasks 只能包含 TaskNode")
        task_ids = tuple(task.task_id for task in self.tasks)
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("任务标识不得重复")
        _immutable_ids("topological_order", self.topological_order, allow_empty=False)
        if set(self.topological_order) != set(task_ids):
            raise ValueError("拓扑顺序必须完整覆盖任务")
        positions = {
            task_id: index for index, task_id in enumerate(self.topological_order)
        }
        known = set(task_ids)
        for task in self.tasks:
            if any(dep not in known for dep in task.depends_on):
                raise ValueError("任务依赖不存在")
            if any(
                positions[dep] >= positions[task.task_id] for dep in task.depends_on
            ):
                raise ValueError("拓扑顺序违反任务依赖")
        if self._depth() > SupervisorLimits().max_dag_depth:
            raise ValueError("DAG 深度超过平台上限")

    def _depth(self) -> int:
        by_id = {task.task_id: task for task in self.tasks}
        memo: dict[str, int] = {}

        def visit(task_id: str, visiting: frozenset[str]) -> int:
            if task_id in memo:
                return memo[task_id]
            if task_id in visiting:
                raise ValueError("任务图存在循环依赖")
            task = by_id[task_id]
            depth = 1 + max(
                (visit(dep, visiting | {task_id}) for dep in task.depends_on),
                default=0,
            )
            memo[task_id] = depth
            return depth

        return max(visit(task.task_id, frozenset()) for task in self.tasks)


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    """仅由受信运行事实生成的任务预算消耗。"""

    iterations: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    cost_microunits: int = 0

    def __post_init__(self) -> None:
        for name in (
            "iterations",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "elapsed_ms",
            "cost_microunits",
        ):
            _non_negative(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class TaskDispatch:
    """Supervisor 对 S1 SupervisorTask 的调度包装，不改变 S1 接口。"""

    task: SupervisorTask
    capability_ids: frozenset[str]
    attempt: int
    revision: int
    fence_token: int
    parent_deadline_epoch_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.task, SupervisorTask):
            raise TypeError("task 必须是 SupervisorTask")
        _immutable_string_set("capability_ids", self.capability_ids)
        _positive("attempt", self.attempt)
        _non_negative("revision", self.revision)
        _non_negative("fence_token", self.fence_token)
        _positive("parent_deadline_epoch_ms", self.parent_deadline_epoch_ms)


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    """单个任务的结构化结果和可信消耗事实。"""

    task_id: str
    agent_id: str | None
    status: TaskExecutionStatus
    result: JsonObject | None
    error_code: str | None
    completed_scope: Sequence[str]
    missing_scope: Sequence[str]
    trusted_usage: BudgetUsage
    attempt: int
    revision: int
    fence_token: int

    def __post_init__(self) -> None:
        _stable_id("task_id", self.task_id)
        if self.agent_id is not None:
            _stable_id("agent_id", self.agent_id)
        if not isinstance(self.status, TaskExecutionStatus):
            raise TypeError("status 必须是 TaskExecutionStatus")
        if self.result is not None and not isinstance(self.result, JsonObject):
            raise TypeError("result 必须是 JsonObject 或 None")
        if self.error_code is not None:
            _text("error_code", self.error_code)
        _immutable_ids("completed_scope", self.completed_scope)
        _immutable_ids("missing_scope", self.missing_scope)
        if set(self.completed_scope).intersection(self.missing_scope):
            raise ValueError("完成范围和缺失范围不得重叠")
        if not isinstance(self.trusted_usage, BudgetUsage):
            raise TypeError("trusted_usage 必须是 BudgetUsage")
        _positive("attempt", self.attempt)
        _non_negative("revision", self.revision)
        _non_negative("fence_token", self.fence_token)
        if self.status is TaskExecutionStatus.SUCCEEDED:
            if self.result is None:
                raise ValueError("成功任务必须包含结构化结果")
            if self.error_code is not None:
                raise ValueError("成功任务不得包含错误")


__all__ = [
    "BudgetUsage",
    "CompletionStatus",
    "SupervisorLimits",
    "TaskDispatch",
    "TaskExecutionStatus",
    "TaskFailureMode",
    "TaskGraph",
    "TaskNode",
    "TaskOutcome",
]
