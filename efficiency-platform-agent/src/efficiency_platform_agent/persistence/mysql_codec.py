"""Run 与 Event 不可变契约的 JSON 编解码。"""

from __future__ import annotations

import json
from typing import Any

from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    JsonValue,
    RunRequest,
)
from efficiency_platform_agent.core.runtime import (
    RunEventRecord,
    RunFailure,
    RunRecord,
    UsageSnapshot,
)


def _plain(value: object) -> object:
    if isinstance(value, JsonObject):
        return {key: _plain(child) for key, child in value.items}
    if isinstance(value, tuple):
        return [_plain(child) for child in value]
    return value


def _immutable(value: object) -> JsonValue:
    if isinstance(value, dict):
        return JsonObject(
            tuple((str(key), _immutable(child)) for key, child in value.items())
        )
    if isinstance(value, list):
        return tuple(_immutable(child) for child in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("持久化 JSON 包含非法值")


def _immutable_object(value: object) -> JsonObject:
    converted = _immutable(value)
    if not isinstance(converted, JsonObject):
        raise TypeError("持久化 JSON 字段必须是对象")
    return converted


def _loads(value: str | dict[str, Any]) -> dict[str, Any]:
    loaded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(loaded, dict):
        raise TypeError("持久化 JSON 顶层必须是对象")
    return loaded


def encode_run(record: RunRecord) -> str:
    """编码完整 Run 快照，禁止只保存状态摘要。"""
    failure = record.failure
    payload = {
        "run_id": record.run_id,
        "request": {
            "request_id": record.request.request_id,
            "tenant_id": record.request.tenant_id,
            "user_id": record.request.user_id,
            "input_text": record.request.input_text,
            "metadata": _plain(record.request.metadata),
        },
        "status": record.status.value,
        "strategy": record.strategy.value if record.strategy is not None else None,
        "budget": {
            "max_iterations": record.budget.max_iterations,
            "max_tool_calls": record.budget.max_tool_calls,
            "max_input_tokens": record.budget.max_input_tokens,
            "max_output_tokens": record.budget.max_output_tokens,
            "timeout_ms": record.budget.timeout_ms,
            "max_cost_microunits": record.budget.max_cost_microunits,
        },
        "budget_state": {
            "consumed": {
                "iterations": record.budget_state.consumed.iterations,
                "tool_calls": record.budget_state.consumed.tool_calls,
                "input_tokens": record.budget_state.consumed.input_tokens,
                "output_tokens": record.budget_state.consumed.output_tokens,
                "cost_microunits": record.budget_state.consumed.cost_microunits,
            },
            "started_at_epoch_ms": record.budget_state.started_at_epoch_ms,
            "deadline_epoch_ms": record.budget_state.deadline_epoch_ms,
        },
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cost_microunits": record.usage.cost_microunits,
            "estimated": record.usage.estimated,
        },
        "version": record.version,
        "output": _plain(record.output),
        "failure": None if failure is None else {
            "code": failure.code,
            "category": failure.category,
            "retryable": failure.retryable,
            "safe_message": failure.safe_message,
        },
        "checkpoint_id": record.checkpoint_id,
        "degraded": record.degraded,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_run(value: str | dict[str, Any]) -> RunRecord:
    """恢复完整 Run 快照并重新执行领域构造校验。"""
    raw = _loads(value)
    request = raw["request"]
    budget = raw["budget"]
    state = raw["budget_state"]
    consumed = state["consumed"]
    usage = raw["usage"]
    failure = raw["failure"]
    return RunRecord(
        run_id=raw["run_id"],
        request=RunRequest(
            request_id=request["request_id"],
            tenant_id=request["tenant_id"],
            user_id=request["user_id"],
            input_text=request["input_text"],
            metadata=_immutable_object(request["metadata"]),
        ),
        status=RunStatus(raw["status"]),
        strategy=None if raw["strategy"] is None else StrategyMode(raw["strategy"]),
        budget=ExecutionBudget(**budget),
        budget_state=BudgetState(
            consumed=BudgetCharge(**consumed),
            started_at_epoch_ms=state["started_at_epoch_ms"],
            deadline_epoch_ms=state["deadline_epoch_ms"],
        ),
        usage=UsageSnapshot(**usage),
        version=raw["version"],
        output=_immutable(raw["output"]),
        failure=None if failure is None else RunFailure(**failure),
        checkpoint_id=raw["checkpoint_id"],
        degraded=raw["degraded"],
    )


def encode_event(event: RunEventRecord) -> str:
    payload = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "run_id": event.run_id,
        "tenant_id": event.tenant_id,
        "sequence": event.sequence,
        "occurred_at_epoch_ms": event.occurred_at_epoch_ms,
        "status": event.status.value,
        "payload": _plain(event.payload),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_event(value: str | dict[str, Any]) -> RunEventRecord:
    raw = _loads(value)
    return RunEventRecord(
        event_id=raw["event_id"],
        event_type=raw["event_type"],
        run_id=raw["run_id"],
        tenant_id=raw["tenant_id"],
        sequence=raw["sequence"],
        occurred_at_epoch_ms=raw["occurred_at_epoch_ms"],
        status=RunStatus(raw["status"]),
        payload=_immutable_object(raw["payload"]),
    )


__all__ = ["decode_event", "decode_run", "encode_event", "encode_run"]
