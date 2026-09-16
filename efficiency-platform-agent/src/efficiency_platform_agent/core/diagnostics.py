"""纯 Agent 侧的受控诊断契约与运行上下文。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from re import fullmatch
from types import TracebackType
from typing import Protocol

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PROJECT_ROOT_NAME = _PROJECT_ROOT.name
_PROVIDER_CALL_ID_PATTERN = r"[A-Za-z0-9._-]{1,128}"


class DiagnosticLevel(StrEnum):
    """诊断记录可使用的固定日志级别。"""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RunDiagnosticContext:
    """当前 Run 可安全关联的固定上下文字段。"""

    run_id: str | None = None
    request_id: str | None = None
    strategy: str | None = None
    agent_name: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticRecord:
    """不含自由正文和载荷的不可变诊断记录。"""

    event_name: str
    component: str
    level: DiagnosticLevel
    capability: str | None = None
    status: str | None = None
    stage: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_call_id: str | None = None
    reason_code: str | None = None
    rule_version: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    error_location: str | None = None
    http_status: int | None = None
    retryable: bool | None = None
    duration_ms: int | None = None
    attempt: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    evidence_valid_count: int | None = None
    evidence_rejected_count: int | None = None

    def __post_init__(self) -> None:
        """在构造阶段拒绝不安全或不可能的诊断事实。"""

        if not self.event_name.strip():
            raise ValueError("event_name 不能为空")
        if not self.component.strip():
            raise ValueError("component 不能为空")
        if self.http_status is not None and (
            type(self.http_status) is not int or not 100 <= self.http_status <= 599
        ):
            raise ValueError("http_status 必须是 100 至 599 的整数")
        for field_name in (
            "duration_ms",
            "attempt",
            "input_tokens",
            "output_tokens",
            "evidence_valid_count",
            "evidence_rejected_count",
        ):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} 必须是非负整数")
        if self.provider_call_id is not None and fullmatch(
            _PROVIDER_CALL_ID_PATTERN, self.provider_call_id
        ) is None:
            raise ValueError("provider_call_id 格式非法")


class DiagnosticRecorderPort(Protocol):
    """同步且不向业务链暴露失败的诊断记录端口。"""

    def record(self, record: DiagnosticRecord) -> None:
        """记录一个已经过白名单约束的诊断事实。"""


class NoopDiagnosticRecorder:
    """测试和未启用日志时使用的无操作诊断记录器。"""

    def record(self, record: DiagnosticRecord) -> None:
        """丢弃诊断记录，避免诊断影响业务执行。"""

        del record


_DIAGNOSTIC_CONTEXT: ContextVar[RunDiagnosticContext | None] = ContextVar(
    "diagnostic_context", default=None
)


@contextmanager
def bind_diagnostic_context(
    *,
    run_id: str | None = None,
    request_id: str | None = None,
    strategy: str | None = None,
    agent_name: str | None = None,
) -> Iterator[RunDiagnosticContext]:
    """为当前执行上下文临时绑定非空的关联标识。"""

    current = current_diagnostic_context()
    context = RunDiagnosticContext(
        run_id=run_id if run_id is not None else current.run_id,
        request_id=request_id if request_id is not None else current.request_id,
        strategy=strategy if strategy is not None else current.strategy,
        agent_name=agent_name if agent_name is not None else current.agent_name,
    )
    token = _DIAGNOSTIC_CONTEXT.set(context)
    try:
        yield context
    finally:
        _DIAGNOSTIC_CONTEXT.reset(token)


def current_diagnostic_context() -> RunDiagnosticContext:
    """返回当前任务隔离的诊断上下文。"""

    return _DIAGNOSTIC_CONTEXT.get() or RunDiagnosticContext()


def safe_exception_location(error: BaseException) -> str | None:
    """提取异常回溯中最后一个项目内帧的安全位置。"""

    frame: TracebackType | None = error.__traceback__
    location: str | None = None
    while frame is not None:
        file_path = Path(frame.tb_frame.f_code.co_filename).resolve()
        if _is_project_frame(file_path):
            location = (
                f"{file_path.name}:{frame.tb_lineno}:{frame.tb_frame.f_code.co_name}"
            )
        frame = frame.tb_next
    return location


def _is_project_frame(file_path: Path) -> bool:
    """判断帧是否属于当前 Agent 工程，兼容同名工作副本的测试路径。"""

    return file_path.is_relative_to(_PROJECT_ROOT) or any(
        ancestor.name == _PROJECT_ROOT_NAME for ancestor in file_path.parents
    )


__all__ = [
    "DiagnosticLevel",
    "DiagnosticRecord",
    "DiagnosticRecorderPort",
    "NoopDiagnosticRecorder",
    "RunDiagnosticContext",
    "bind_diagnostic_context",
    "current_diagnostic_context",
    "safe_exception_location",
]
