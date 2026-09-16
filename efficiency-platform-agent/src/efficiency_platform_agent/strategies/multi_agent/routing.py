"""Supervisor 条件路由，返回稳定字符串出口。"""

from __future__ import annotations


def route_after_reconcile(state: dict[str, object]) -> str:
    """根据可观察状态选择下一节点，不导入编排框架。"""

    if state.get("cancel_requested"):
        return "cancel"
    if state.get("pending_input"):
        return "wait_input"
    status = str(state.get("completion_status") or "")
    if status in {"failed", "cancelled"}:
        return "fail" if status == "failed" else "cancel"
    statuses = state.get("task_statuses")
    if (
        isinstance(statuses, dict)
        and statuses
        and all(value in {"succeeded", "skipped"} for value in statuses.values())
    ):
        return "aggregate"
    return "schedule_wave"


def route_after_aggregate(state: dict[str, object]) -> str:
    """根据聚合状态决定等待、失败、取消或继续 assembly。"""

    status = str(state.get("completion_status") or "")
    if status == "waiting_input":
        return "wait_input"
    if status == "cancelled":
        return "cancel"
    if status == "failed":
        return "fail"
    return "assemble"


__all__ = ["route_after_aggregate", "route_after_reconcile"]
