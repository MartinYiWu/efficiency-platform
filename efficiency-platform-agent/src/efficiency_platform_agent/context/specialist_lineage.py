"""将D05受信切片接入现有专家执行，不携父history/checkpoint或未知外部事实。"""

from collections.abc import Awaitable, Callable
from functools import wraps
from hashlib import sha256
from typing import Any, cast

from efficiency_platform_agent.core.context_projection import SpecialistContextSlice
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_lineage import (
    current_specialist_registry,
    registered_specialist_input,
    specialist_lineage_session,
)
from efficiency_platform_agent.core.run import SupervisorTask
from efficiency_platform_agent.core.run_context_binding import current_run_context


def lineage_session[F: Callable[..., Awaitable[Any]]](function: F) -> F:
    @wraps(function)
    async def invoke(*args: Any, **kwargs: Any) -> Any:
        with specialist_lineage_session():
            return await function(*args, **kwargs)

    return cast(F, invoke)


def lineage_input[F: Callable[..., Awaitable[Any]]](function: F) -> F:
    @wraps(function)
    async def invoke(self: Any, task: SupervisorTask) -> Any:
        binding = current_run_context()
        if binding is not None and binding.memory_context is not None:
            evidence = getattr(self, "evidence_pack", None)
            if evidence is not None and getattr(evidence, "records", True):
                raise ValueError("MEMORY_SPECIALIST_EVIDENCE_SOURCE_REQUIRED")
        with registered_specialist_input(task):
            return await function(self, task)

    return cast(F, invoke)


def register_task_slice(
    task: SupervisorTask,
    *,
    goal: str,
    upstream: tuple[str, ...],
    parent_plan_digest: str,
) -> None:
    binding = current_run_context()
    if binding is None or binding.memory_context is None:
        return
    registry = current_specialist_registry()
    if registry is None:
        raise ValueError("MEMORY_SPECIALIST_LINEAGE_ADAPTER_REQUIRED")
    context = binding.memory_context
    version = sha256(goal.encode()).hexdigest()
    # 原intent完整请求已见input_dependencies；goal/conditions/plan继承这份传递闭包，
    # 不是packet里未见的授权偏好，也不把父history正文送给子任务。
    current = tuple(
        dependency
        for dependency in context.input_dependencies
        if dependency.source_type == "CURRENT_USER_MESSAGE"
        and dependency.source_version == version
    )
    if not current:
        raise ValueError("MEMORY_SPECIALIST_CURRENT_SOURCE_REQUIRED")
    dependencies = list(context.input_dependencies)
    for task_id in upstream:
        dependencies.extend(registry.dependencies(task_id))
    sources = tuple(dict.fromkeys(dependencies))
    purposes = {
        grant.purpose
        for grant in context.execution_grants
        if grant.execution_agent_id == task.target_agent
    }
    if len(purposes) != 1:
        raise ValueError("MEMORY_SPECIALIST_PURPOSE_NOT_PUBLISHED")
    scope = ExecutionScope(
        binding.conversation,
        binding.task_id,
        binding.execution_id,
        task.task_id,
        next(iter(purposes)),
        task.target_agent,
    )
    registry.register(
        task,
        SpecialistContextSlice(
            "specialist-context-slice/1",
            scope,
            goal,
            (),
            sources,
            (),
            task.allowed_tools,
            "operation-specialist-result/1",
            context.policy.version,
            context.packet.parent_authorization_ref,
            (task.task_id,),
        ),
        parent_plan_digest,
    )
