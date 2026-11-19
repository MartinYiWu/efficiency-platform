"""可信Supervisor每次运行的有界输入切片回执；不提供新的源或预算授权。"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from hashlib import sha256

from .context_control import ContextManifest
from .context_projection import SpecialistContextSlice
from .memory import SourceDependency
from .run import SupervisorTask
from .run_context_binding import RunContextBinding, current_run_context


@dataclass(frozen=True, slots=True)
class RegisteredSpecialistInput:
    slice: SpecialistContextSlice
    input_digest: str
    parent_request_digest: str
    parent_plan_digest: str


class SpecialistLineageRegistry:
    """仅父调度代码签入实际已裁剪输入；不能从模型返回的context字段重建。"""

    def __init__(self, binding: RunContextBinding):
        if binding.memory_context is None:
            raise ValueError("MEMORY_SPECIALIST_PARENT_REQUIRED")
        self.binding = binding
        self.active = True
        self._inputs: dict[str, RegisteredSpecialistInput] = {}
        self._observed: dict[str, tuple[SourceDependency, ...]] = {}
        self._parent_plan_digest: str | None = None

    @staticmethod
    def _digest(task: SupervisorTask) -> str:
        return sha256(repr((task.input_data, task.allowed_tools)).encode()).hexdigest()

    def register(
        self,
        task: SupervisorTask,
        slice_: SpecialistContextSlice,
        parent_plan_digest: str,
    ) -> None:
        scope = slice_.scope
        context = self.binding.memory_context
        if (
            not self.active
            or context is None
            or current_run_context() != self.binding
            or (scope.conversation, scope.task_id, scope.execution_id)
            != (
                self.binding.conversation,
                self.binding.task_id,
                self.binding.execution_id,
            )
            or (scope.subtask_id, scope.execution_agent_id)
            != (task.task_id, task.target_agent)
            or not slice_.source_dependencies
            or not set(slice_.source_dependencies).issubset(
                context.packet.safety_dependencies
            )
        ):
            raise ValueError("MEMORY_SPECIALIST_SLICE_BINDING_INVALID")
        if len(parent_plan_digest) != 64 or any(
            character not in "0123456789abcdef" for character in parent_plan_digest
        ):
            raise ValueError("MEMORY_SPECIALIST_PARENT_PLAN_REQUIRED")
        if (
            self._parent_plan_digest is not None
            and self._parent_plan_digest != parent_plan_digest
        ):
            raise ValueError("MEMORY_SPECIALIST_PARENT_PLAN_CHANGED")
        self._parent_plan_digest = parent_plan_digest
        receipt = RegisteredSpecialistInput(
            slice_, self._digest(task), context.request_digest, parent_plan_digest
        )
        previous = self._inputs.get(task.task_id)
        if previous is not None and previous != receipt:
            raise ValueError("MEMORY_SPECIALIST_SLICE_CHANGED")
        if previous is None and len(self._inputs) >= 128:
            raise ValueError("MEMORY_SPECIALIST_SLICE_LIMIT")
        self._inputs[task.task_id] = receipt

    def input(self, task: SupervisorTask) -> RegisteredSpecialistInput:
        receipt = self._inputs.get(task.task_id)
        if (
            not self.active
            or current_run_context() != self.binding
            or receipt is None
            or receipt.input_digest != self._digest(task)
            or receipt.slice.scope.execution_agent_id != task.target_agent
        ):
            raise ValueError("MEMORY_SPECIALIST_INPUT_NOT_REGISTERED")
        return receipt

    def dependencies(self, task_id: str) -> tuple[SourceDependency, ...]:
        receipt = self._inputs.get(task_id)
        if not self.active or receipt is None:
            raise ValueError("MEMORY_SPECIALIST_UPSTREAM_LINEAGE_REQUIRED")
        return tuple(
            dict.fromkeys(
                (*receipt.slice.source_dependencies, *self._observed.get(task_id, ()))
            )
        )

    def record_manifest(self, manifest: ContextManifest) -> None:
        if not self.active:
            raise ValueError("MEMORY_SPECIALIST_PARENT_FRAME_CLOSED")
        receipt = self._inputs.get(manifest.scope.subtask_id)
        if receipt is None:
            return
        context = self.binding.memory_context
        if (
            context is None
            or manifest.scope != receipt.slice.scope
            or not set(manifest.safety_dependencies).issubset(
                context.packet.safety_dependencies
            )
        ):
            raise ValueError("MEMORY_SPECIALIST_RESULT_LINEAGE_MISMATCH")
        previous = self._observed.get(manifest.scope.subtask_id, ())
        self._observed[manifest.scope.subtask_id] = tuple(
            dict.fromkeys((*previous, *manifest.safety_dependencies))
        )


_registry: ContextVar[SpecialistLineageRegistry | None] = ContextVar(
    "specialist_lineage_registry", default=None
)
_input: ContextVar[RegisteredSpecialistInput | None] = ContextVar(
    "registered_specialist_input", default=None
)


def current_specialist_registry() -> SpecialistLineageRegistry | None:
    return _registry.get()


def current_specialist_input() -> RegisteredSpecialistInput | None:
    return _input.get()


def record_specialist_manifest(manifest: ContextManifest) -> None:
    registry = _registry.get()
    if registry is not None:
        registry.record_manifest(manifest)


@contextmanager
def specialist_lineage_session() -> Iterator[None]:
    binding = current_run_context()
    registry = (
        SpecialistLineageRegistry(binding)
        if binding is not None and binding.memory_context is not None
        else None
    )
    token = _registry.set(registry)
    try:
        yield
    finally:
        if registry is not None:
            registry.active = False
        _registry.reset(token)


@contextmanager
def registered_specialist_input(task: SupervisorTask) -> Iterator[None]:
    binding = current_run_context()
    if binding is None or binding.memory_context is None:
        yield
        return
    registry = _registry.get()
    if registry is None:
        raise ValueError("MEMORY_SPECIALIST_LINEAGE_ADAPTER_REQUIRED")
    token = _input.set(registry.input(task))
    try:
        yield
    finally:
        _input.reset(token)
