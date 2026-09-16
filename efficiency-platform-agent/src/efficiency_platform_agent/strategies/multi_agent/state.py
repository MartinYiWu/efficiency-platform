"""多 Agent Supervisor 的可检查、可恢复状态结构。"""

from __future__ import annotations

import math
from typing import TypedDict, cast


class OperationSupervisorState(TypedDict):
    """只允许 JSON/msgpack 基础值的 Supervisor 状态。"""

    run_id: str
    tenant_id: str
    user_id: str
    strategy_payload_schema_version: str
    strategy_payload: dict[str, object]
    parent_deadline_epoch_ms: int
    operation_request: dict[str, object] | None
    operation_task: dict[str, object] | None
    operation_context: dict[str, object] | None
    operation_plan: dict[str, object] | None
    plan_id: str | None
    plan_contract_version: str | None
    plan_revision: int
    task_graph: dict[str, object] | None
    task_statuses: dict[str, str]
    attempts: dict[str, int]
    task_revisions: dict[str, int]
    fence_token: int
    budget_ledger: dict[str, object]
    outcomes: dict[str, dict[str, object]]
    pending_input: dict[str, object] | None
    completion_status: str | None
    output: object
    error_code: str | None


_REQUIRED_FIELDS = frozenset(OperationSupervisorState.__annotations__)
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"task", "plan", "graph", "status", "outcome", "operation_task", "operation_plan"}
)


def _validate_json_value(value: object, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"STATE_NOT_SERIALIZABLE:{path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"STATE_NOT_SERIALIZABLE:{path}")  # noqa: TRY004  # 对外统一状态错误码
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"STATE_NOT_SERIALIZABLE:{path}")


def validate_supervisor_state(state: OperationSupervisorState) -> None:
    """拒绝运行时对象、预计算状态和不完整的 Supervisor 状态。"""

    if not isinstance(state, dict):
        raise ValueError("STATE_INVALID:state")  # noqa: TRY004  # 对外统一状态错误码
    keys = set(state)
    if keys != _REQUIRED_FIELDS:
        raise ValueError("STATE_INVALID:fields")
    _validate_json_value(state, path="state")
    raw_state = cast(dict[str, object], state)
    for field_name in (
        "run_id",
        "tenant_id",
        "user_id",
        "strategy_payload_schema_version",
    ):
        value = raw_state[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"STATE_INVALID:{field_name}")
    for field_name in ("parent_deadline_epoch_ms",):
        value = raw_state[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"STATE_INVALID:{field_name}")
    for field_name in ("plan_revision", "fence_token"):
        value = raw_state[field_name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"STATE_INVALID:{field_name}")
    payload = raw_state["strategy_payload"]
    if not isinstance(payload, dict):
        raise ValueError("STATE_INVALID:strategy_payload")  # noqa: TRY004  # 对外统一状态错误码
    for key in payload:
        if key.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            raise ValueError(f"PRECOMPUTED_STATE_FORBIDDEN:{key}")
    for field_name in ("task_statuses", "attempts", "task_revisions", "outcomes"):
        mapping = raw_state[field_name]
        if not isinstance(mapping, dict) or any(
            not isinstance(key, str) for key in mapping
        ):
            raise ValueError(f"STATE_INVALID:{field_name}")
    if any(
        not isinstance(value, str)
        for value in cast(dict[str, object], raw_state["task_statuses"]).values()
    ):
        raise ValueError("STATE_INVALID:task_statuses")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in cast(dict[str, object], raw_state["attempts"]).values()
    ):
        raise ValueError("STATE_INVALID:attempts")
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in cast(dict[str, object], raw_state["task_revisions"]).values()
    ):
        raise ValueError("STATE_INVALID:task_revisions")


__all__ = ["OperationSupervisorState", "validate_supervisor_state"]
