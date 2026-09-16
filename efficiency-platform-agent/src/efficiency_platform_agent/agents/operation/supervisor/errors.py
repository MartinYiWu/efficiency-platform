"""运营 Supervisor 计划编译的稳定错误契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SupervisorPlanErrorCode(StrEnum):
    """计划编译器可被调用方稳定识别的拒绝原因。"""

    PLAN_EMPTY = "PLAN_EMPTY"
    TASK_LIMIT_EXCEEDED = "TASK_LIMIT_EXCEEDED"
    DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
    DAG_CYCLE = "DAG_CYCLE"
    DAG_DEPTH_EXCEEDED = "DAG_DEPTH_EXCEEDED"
    INVALID_FAILURE_BEHAVIOR = "INVALID_FAILURE_BEHAVIOR"
    STEP_BUDGET_EXCEEDS_PLAN = "STEP_BUDGET_EXCEEDS_PLAN"
    DUPLICATE_TASK_ID = "DUPLICATE_TASK_ID"


@dataclass(frozen=True, slots=True)
class SupervisorPlanErrorDetail:
    """计划编译错误的安全结构化信息。"""

    code: SupervisorPlanErrorCode
    safe_message: str
    task_id: str | None = None


class SupervisorPlanError(ValueError):
    """计划在创建调度任务前被拒绝时抛出的领域异常。"""

    def __init__(
        self,
        code: SupervisorPlanErrorCode,
        safe_message: str,
        *,
        task_id: str | None = None,
    ) -> None:
        self.detail = SupervisorPlanErrorDetail(code, safe_message, task_id)
        super().__init__(code.value)


__all__ = [
    "SupervisorPlanError",
    "SupervisorPlanErrorCode",
    "SupervisorPlanErrorDetail",
]
