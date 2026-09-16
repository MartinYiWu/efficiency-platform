"""运营 Supervisor 入站策略载荷契约。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from efficiency_platform_agent.agents.operation.contracts.task import OperationRequest
from efficiency_platform_agent.core.run import JsonObject, JsonValue
from efficiency_platform_agent.core.runtime import StrategyPayload


class OperationStrategyPayloadV1(BaseModel):
    """只允许携带原始运营请求，禁止预计算任务图和结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    contract_version: Literal["operation-strategy-payload/1"] = (
        "operation-strategy-payload/1"
    )
    operation_request: Any


class OperationStrategyPayloadAdapter:
    """将 S2 JSON 载荷校验为不可变策略载荷。"""

    schema_version = "operation-strategy-payload/1"
    allowed_keys = frozenset({"operation_request"})
    _forbidden_state_keys = frozenset(
        {
            "task",
            "plan",
            "graph",
            "status",
            "outcome",
            "operation_task",
            "operation_plan",
            "task_graph",
            "task_statuses",
            "outcomes",
            "completion_status",
        }
    )

    def adapt(self, schema_version: str, payload: JsonObject) -> StrategyPayload:
        if schema_version != self.schema_version:
            raise ValueError("STRATEGY_PAYLOAD_SCHEMA_UNSUPPORTED")
        if not isinstance(payload, JsonObject):
            raise TypeError("策略载荷必须是JsonObject")
        keys = tuple(key for key, _ in payload.items)
        if set(keys) != self.allowed_keys:
            forbidden = next(
                (key for key in keys if key not in self.allowed_keys), None
            )
            if forbidden is not None:
                raise ValueError(f"PRECOMPUTED_STATE_FORBIDDEN:{forbidden}")
            raise ValueError("策略载荷必须且只能包含operation_request")
        value = dict(payload.items)["operation_request"]
        if not isinstance(value, JsonObject):
            raise ValueError("operation_request必须是JsonObject")  # noqa: TRY004
        self._reject_precomputed(value)
        return StrategyPayload(schema_version, payload)

    @classmethod
    def _reject_precomputed(
        cls, value: JsonObject, path: str = "operation_request"
    ) -> None:
        """递归拒绝藏在原始请求中的预计算状态字段。"""

        for key, child in value.items:
            if key.lower() in cls._forbidden_state_keys:
                raise ValueError(f"PRECOMPUTED_STATE_FORBIDDEN:{path}.{key}")
            if isinstance(child, JsonObject):
                cls._reject_precomputed(child, f"{path}.{key}")
            elif isinstance(child, tuple):
                for item in child:
                    if isinstance(item, JsonObject):
                        cls._reject_precomputed(item, f"{path}.{key}")


def _coerce_json_value(value: object) -> JsonValue:
    """把检查点反序列化后的普通容器恢复为不可变 JSON 值。"""

    if isinstance(value, JsonObject):
        return value
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _coerce_json_value(child)) for key, child in value.items())
        )
    if isinstance(value, (tuple, list)):
        return tuple(_coerce_json_value(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("JSON 载荷包含不支持的值类型")


def _coerce_json_object(value: object) -> JsonObject:
    """将普通映射转换为运营请求解码所需的 JsonObject。"""

    normalized = _coerce_json_value(value)
    if not isinstance(normalized, JsonObject):
        raise TypeError("operation_request 必须是对象")
    return normalized


def decode_operation_request(
    value: JsonObject | Mapping[str, object],
) -> OperationRequest:
    """从受控 JSON 对象解码运营请求；运行时对象可由测试适配器直接传入。"""

    value = _coerce_json_object(value)
    raw = dict(value.items)
    OperationStrategyPayloadAdapter._reject_precomputed(value)
    request = raw.get("request")
    if not isinstance(request, JsonObject):
        raise ValueError("operation_request.request缺失")  # noqa: TRY004
    req_raw = dict(request.items)
    from efficiency_platform_agent.core.run import RunRequest

    base = RunRequest(
        request_id=str(req_raw.get("request_id", "")),
        tenant_id=str(req_raw.get("tenant_id", "")),
        user_id=str(req_raw.get("user_id", "")),
        input_text=str(req_raw.get("input_text", "")),
    )
    return OperationRequest(
        contract_version=str(raw.get("contract_version", "operation-request/1")),
        request=base,
        operation_id=str(raw.get("operation_id", base.request_id)),
        session_id=cast(str | None, raw.get("session_id"))
        if isinstance(raw.get("session_id"), str)
        else None,
        parent_task_id=cast(str | None, raw.get("parent_task_id"))
        if isinstance(raw.get("parent_task_id"), str)
        else None,
        requested_domains=frozenset(),
        requested_deliverables=(),
    )


__all__ = [
    "OperationStrategyPayloadAdapter",
    "OperationStrategyPayloadV1",
    "decode_operation_request",
]
