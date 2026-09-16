"""Supervisor 的框架中立节点，只返回状态补丁和事件意图。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from efficiency_platform_agent.agents.operation.contracts.evidence import EvidencePack
from efficiency_platform_agent.agents.operation.contracts.planning import OperationPlan
from efficiency_platform_agent.agents.operation.contracts.ports import (
    S2OperationAssemblyPort,
    S2OperationIntentPort,
    S2OperationPlanningPort,
)
from efficiency_platform_agent.agents.operation.contracts.profiles import (
    OperationContext,
)
from efficiency_platform_agent.agents.operation.contracts.task import (
    OperationRequest,
    OperationTaskSpec,
)
from efficiency_platform_agent.contracts.operation_strategy import (
    decode_operation_request,
)
from efficiency_platform_agent.core.run import JsonObject, JsonValue


def _plain(value: object) -> object:
    """将常用不可变值对象转换为可检查的 JSON 结构。"""

    if isinstance(value, JsonObject):
        return {key: _plain(child) for key, child in value.items}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if hasattr(value, "__dataclass_fields__"):
        return {
            # 新增契约字段对旧的内存 fixture 保持读取兼容，缺失时采用安全默认值。
            name: _plain(getattr(value, name, None))
            for name in value.__dataclass_fields__
        }
    return str(value)


def _json_value(value: object) -> JsonValue:
    """将领域值对象转换为 S2 可接受的不可变 JSON 值。"""

    plain = _plain(value)
    if isinstance(plain, dict):
        return JsonObject(
            tuple((str(key), _json_value(child)) for key, child in plain.items())
        )
    if isinstance(plain, list):
        return tuple(_json_value(item) for item in plain)
    return cast(JsonValue, plain)


@dataclass
class SupervisorDependencies:
    """由组合根注入的 S3 端口，不写入图状态。"""

    intent: S2OperationIntentPort | None
    planning: S2OperationPlanningPort | None
    assembly: S2OperationAssemblyPort | None
    context_builder: Callable[[OperationTaskSpec], object] | object | None = None
    plan_compiler: Callable[[object], object] | object | None = None
    scheduler: object | None = None
    aggregator: object | None = None
    runtime_objects: dict[str, dict[str, object]] = field(default_factory=dict)

    def _cache(self, state: dict[str, object]) -> dict[str, object]:
        run_id = str(state.get("run_id", "unknown"))
        return self.runtime_objects.setdefault(run_id, {})


def decode_operation_request_node(
    state: dict[str, object], dependencies: SupervisorDependencies | None = None
) -> dict[str, object]:
    """校验载荷并解码原始运营请求，拒绝预计算状态。"""

    payload = state.get("strategy_payload")
    if isinstance(payload, JsonObject):
        payload = dict(payload.items)
    if not isinstance(payload, dict) or set(payload) != {"operation_request"}:
        raise ValueError("PRECOMPUTED_STATE_FORBIDDEN")
    value = payload["operation_request"]
    if isinstance(value, OperationRequest):
        request = value
    elif isinstance(value, (JsonObject, dict)):
        request = decode_operation_request(value)
    else:
        raise ValueError("operation_request无效")  # noqa: TRY004
    if dependencies is not None:
        dependencies._cache(state)["operation_request"] = request
    # LangGraph 只会把节点返回的键写入后续 State；显式携带运行身份和
    # 截止时间，避免后续节点丢失 Supervisor 的缓存分区键。
    result: dict[str, object] = {
        "operation_request": _plain(request),
    }
    for key in (
        "run_id",
        "tenant_id",
        "user_id",
        "request_id",
        "parent_deadline_epoch_ms",
        "strategy_payload_schema_version",
        "strategy_payload",
    ):
        if key in state:
            result[key] = state[key]
    return result


def normalize_intent_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """调用 S3 意图端口一次。"""

    request = dependencies._cache(state).get("operation_request")
    if not isinstance(request, OperationRequest):
        raise ValueError("operation_request未解码")  # noqa: TRY004
    if dependencies.intent is None:
        raise ValueError("运营意图端口未配置")
    task = dependencies.intent.normalize(request)
    dependencies._cache(state)["operation_task"] = task
    return {"operation_task": _plain(task)}


def build_operation_context_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """从已归一化任务构建最小运营上下文。"""

    task = dependencies._cache(state).get("operation_task")
    if not isinstance(task, OperationTaskSpec):
        raise ValueError("operation_task未归一化")  # noqa: TRY004
    builder = dependencies.context_builder
    if builder is None:
        raise ValueError("运营上下文构建器未配置")
    elif callable(builder):
        context = builder(task)
    else:
        build = getattr(builder, "build", None)
        if not callable(build):
            raise ValueError("运营上下文构建器无效")
        context = build(task)
    dependencies._cache(state)["operation_context"] = context
    return {"operation_context": _plain(context)}


def build_plan_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """调用 S3 计划端口一次。"""

    cache = dependencies._cache(state)
    task = cache.get("operation_task")
    context = cache.get("operation_context")
    if not isinstance(task, OperationTaskSpec):
        raise ValueError("operation_task未归一化")  # noqa: TRY004
    if dependencies.planning is None:
        raise ValueError("运营计划端口未配置")
    if not isinstance(context, OperationContext):
        raise TypeError("运营上下文无效")
    plan = dependencies.planning.build_plan(task, context)
    cache["operation_plan"] = plan
    return {"operation_plan": _plain(plan), "plan_id": getattr(plan, "plan_id", None)}


def compile_plan_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """把 S3 计划交给 Supervisor 编译器，不自行推断业务步骤。"""

    plan = dependencies._cache(state).get("operation_plan")
    compiler = dependencies.plan_compiler
    if plan is None or compiler is None:
        return {}
    if callable(compiler):
        graph = compiler(plan)
    else:
        compile_method = getattr(compiler, "compile", None)
        if not callable(compile_method):
            raise TypeError("计划编译器无效")
        graph = compile_method(plan)
    dependencies._cache(state)["task_graph"] = graph
    return {"task_graph": _plain(graph)}


def assemble_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """使用聚合后的证据调用 S3 assembly 端口一次。"""

    cache = dependencies._cache(state)
    task = cache.get("operation_task")
    plan = cache.get("operation_plan")
    evidence = cache.get("evidence_pack")
    if task is None or plan is None:
        raise ValueError("assembly输入不完整")
    if dependencies.assembly is None:
        raise ValueError("运营 assembly 端口未配置")
    if not isinstance(task, OperationTaskSpec) or not isinstance(plan, OperationPlan):
        raise TypeError("assembly任务或计划类型无效")
    if evidence is None:
        evidence = EvidencePack(
            "evidence-pack/1", f"{task.task_id}.evidence", task.task_id, (), ()
        )
    if not isinstance(evidence, EvidencePack):
        raise TypeError("聚合证据包无效")
    result = dependencies.assembly.assemble(task, plan, evidence)
    cache["deliverable"] = result
    return {
        "output": JsonObject(
            (
                ("content", "运营交付物已生成"),
                ("deliverable_bundle", _json_value(result)),
            )
        ),
        "completion_status": "complete",
    }


def initialize_budget_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """初始化任务状态和预算快照。"""

    graph = dependencies._cache(state).get("task_graph")
    raw_statuses = state.get("task_statuses", {})
    statuses = dict(raw_statuses) if isinstance(raw_statuses, Mapping) else {}
    if graph is not None and hasattr(graph, "tasks"):
        statuses = {
            task.task_id: ("ready" if not task.depends_on else "pending")
            for task in graph.tasks
        }
    return {
        "task_statuses": statuses,
        "budget_ledger": (
            dict(cast(Mapping[str, object], state["budget_ledger"]))
            if isinstance(state.get("budget_ledger"), Mapping)
            else {}
        ),
    }


async def schedule_wave_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """执行一轮有界调度，并只缓存结构化结果。"""

    scheduler = dependencies.scheduler
    if scheduler is None:
        return {"wave_events": []}
    run_wave = getattr(scheduler, "run_wave", None)
    if not callable(run_wave):
        raise TypeError("Supervisor 调度器无效")
    wave = await run_wave(state)
    cache = dependencies._cache(state)
    cache["wave_result"] = wave
    outcomes = tuple(getattr(wave, "outcomes", ()))
    cache.setdefault("outcomes", {})
    cached_outcomes = cache["outcomes"]
    if isinstance(cached_outcomes, dict):
        cached_outcomes.update({item.task_id: item for item in outcomes})
    cancelled = (
        bool(state.get("cancel_requested"))
        or bool(getattr(wave, "cancelled", False))
        or any(
            getattr(item.status, "value", item.status) == "cancelled"
            for item in outcomes
        )
    )
    return {
        "wave_events": list(getattr(wave, "event_intents", ())),
        "outcomes": {item.task_id: _plain(item) for item in outcomes},
        "cancel_requested": cancelled,
    }


def reconcile_wave_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """将可信波次结果映射为任务状态，不写事件存储。"""

    wave = dependencies._cache(state).get("wave_result")
    raw_statuses = state.get("task_statuses", {})
    statuses = dict(raw_statuses) if isinstance(raw_statuses, Mapping) else {}
    for outcome in getattr(wave, "outcomes", ()):
        statuses[outcome.task_id] = outcome.status.value
    graph = dependencies._cache(state).get("task_graph")
    if graph is not None and hasattr(graph, "tasks"):
        for node in graph.tasks:
            if statuses.get(node.task_id) == "pending" and all(
                statuses.get(dep) == "succeeded" for dep in node.depends_on
            ):
                statuses[node.task_id] = "ready"
    return {"task_statuses": statuses}


def aggregate_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """调用结果聚合器，并保留证据包供 assembly 使用。"""

    aggregator = dependencies.aggregator
    cache = dependencies._cache(state)
    graph = cache.get("task_graph")
    wave = cache.get("wave_result")
    if aggregator is None or graph is None:
        return {}
    cached = cache.get("outcomes", {})
    outcomes = (
        tuple(cached.values())
        if isinstance(cached, dict)
        else tuple(getattr(wave, "outcomes", ()))
    )
    aggregate = getattr(aggregator, "aggregate", None)
    if not callable(aggregate):
        raise TypeError("Supervisor 聚合器无效")
    result = aggregate(graph, outcomes)
    cache["aggregation"] = result
    if result.evidence_pack is not None:
        cache["evidence_pack"] = result.evidence_pack
    return {
        "completion_status": result.completion_status.value,
        "pending_input": {"missing_scope": list(result.missing_scope)}
        if result.completion_status.value == "waiting_input"
        else None,
    }


def wait_input_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """生成不含补充正文的检查点绑定，并进入等待状态。"""

    return {
        "next_status": "waiting_input",
        "pending_input": state.get("pending_input") or {"required": True},
        "resume_binding": {
            "request_id": state.get("request_id", ""),
            "plan_revision": state.get("plan_revision", 0),
            "fence_token": state.get("fence_token", 0),
        },
    }


def cancel_node(
    state: dict[str, object], dependencies: SupervisorDependencies
) -> dict[str, object]:
    """生成取消状态补丁并递增 fence，迟到结果无法进入输出。"""

    raw_fence = state.get("fence_token", 0)
    fence = raw_fence if isinstance(raw_fence, int) else 0
    return {
        "next_status": "cancelled",
        "completion_status": "cancelled",
        "fence_token": fence + 1,
    }


__all__ = [
    "SupervisorDependencies",
    "aggregate_node",
    "assemble_node",
    "build_operation_context_node",
    "build_plan_node",
    "cancel_node",
    "compile_plan_node",
    "decode_operation_request_node",
    "initialize_budget_node",
    "normalize_intent_node",
    "reconcile_wave_node",
    "schedule_wave_node",
    "wait_input_node",
]
