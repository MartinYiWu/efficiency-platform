"""Specialist 运行适配边界，不包含具体业务规则或外部 IO。"""

from __future__ import annotations

import inspect
from dataclasses import fields, is_dataclass

from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.contracts.task import OperationTaskSpec
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    JsonObject,
    JsonValue,
    RunResult,
    SupervisorTask,
)

from .contracts import SpecialistExecutionInput, SpecialistExecutionResult


def _scan(value: object) -> None:
    """递归拒绝分析原始行和不可跨边界的数据集对象。"""

    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {"rows", "raw_rows", "dataframe"}:
                raise ValueError("分析原始行不得进入调度上下文")
            _scan(child)
    elif isinstance(value, JsonObject):
        for key, child in value.items:
            if key.lower() in {"rows", "raw_rows", "dataframe"}:
                raise ValueError("分析原始行不得进入调度上下文")
            _scan(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _scan(child)


def decode_specialist_task(task: SupervisorTask) -> SpecialistExecutionInput:
    """从 S4 裁剪后的 SupervisorTask 解码 Specialist 输入。"""

    if not isinstance(task, SupervisorTask):
        raise TypeError("task必须是SupervisorTask")
    _scan(task.input_data)
    _scan(task.context_view)
    raw = dict(task.input_data.items)
    operation_task = raw.get("operation_task")
    operation_context = raw.get("operation_context")
    if not isinstance(operation_task, OperationTaskSpec) or not isinstance(
        operation_context, OperationContext
    ):
        raise ValueError(  # noqa: TRY004  # 统一把领域上下文拒绝映射为输入契约错误
            "SPECIALIST_INPUT_INVALID:domain_context"
        )
    return SpecialistExecutionInput(
        "operation-specialist-input/1",
        task.task_id,
        str(raw.get("tenant_id", "")),
        operation_task,
        operation_context,
    )


def _json(value: object) -> JsonValue:
    """把契约值转换为 S4 JsonObject，不输出原始文本或异常。"""

    if isinstance(value, JsonObject):
        return value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list, frozenset)):
        return tuple(_json(item) for item in value)
    if isinstance(value, dict):
        return JsonObject(tuple((str(k), _json(v)) for k, v in value.items()))
    if is_dataclass(value):
        return JsonObject(
            tuple(
                (field.name, _json(getattr(value, field.name)))
                for field in fields(value)
            )
        )
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def encode_specialist_result(
    result: SpecialistExecutionResult, parent_run_id: str
) -> RunResult:
    """使用 S4 官方结果信封映射 Specialist 结果。"""

    if not isinstance(result, SpecialistExecutionResult):
        raise TypeError("result必须是SpecialistExecutionResult")
    raw = {
        "contract_version": result.contract_version,
        "task_id": result.task_id,
        "completed_scope": result.completed_scope,
        "missing_scope": result.missing_scope,
        "deliverable_bundle": result.deliverable_bundle,
        "evidence_pack": result.evidence_pack,
        "quality_report": result.quality_report,
        "assumptions": result.assumptions,
        "warnings": result.warnings,
        "error_code": result.error_code,
        "requested_capability": result.requested_capability,
        "revision_request": result.revision_request,
        "usage": result.usage,
    }
    output = JsonObject(tuple((key, _json(value)) for key, value in raw.items()))
    status = RunStatus.FAILED if result.error_code else RunStatus.SUCCEEDED
    return RunResult(parent_run_id, status, StrategyMode.MULTI_AGENT, output)


class OperationSpecialistRuntime:
    """按固定顺序校验输入、调用注入模型并编码结果。"""

    def __init__(self, model=None) -> None:
        self.model = model

    async def run(
        self, task: SupervisorTask, execution_input: SpecialistExecutionInput
    ) -> RunResult:
        if not isinstance(task, SupervisorTask) or not isinstance(
            execution_input, SpecialistExecutionInput
        ):
            raise TypeError("Specialist运行参数无效")
        if task.task_id != execution_input.task_id:
            raise ValueError("SPECIALIST_TASK_MISMATCH")
        expected_tenant = dict(task.input_data.items).get("tenant_id")
        if (
            isinstance(expected_tenant, str)
            and expected_tenant != execution_input.tenant_id
        ):
            raise ValueError("SPECIALIST_TENANT_MISMATCH")
        if self.model is None:
            raise ValueError("SPECIALIST_MODEL_UNAVAILABLE")
        call = getattr(self.model, "run", None) or getattr(self.model, "invoke", None)
        if call is None:
            raise TypeError("模型缺少run端口")
        value = call(execution_input)
        if inspect.isawaitable(value):
            value = await value
        if not isinstance(value, SpecialistExecutionResult):
            raise ValueError("SPECIALIST_OUTPUT_SCHEMA_INVALID")  # noqa: TRY004
        return encode_specialist_result(value, task.parent_run_id)


__all__ = [
    "OperationSpecialistRuntime",
    "decode_specialist_task",
    "encode_specialist_result",
]
