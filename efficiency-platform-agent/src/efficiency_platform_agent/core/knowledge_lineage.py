"""客服实际完整请求与逐文档安全来源的进程内回执，不创建授权。"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from .memory import SourceDependency
from .run import ProviderRequest


@dataclass(frozen=True, slots=True)
class KnowledgeStageInput:
    request: ProviderRequest
    dependencies: tuple[SourceDependency, ...]


_current: ContextVar[KnowledgeStageInput | None] = ContextVar(
    "knowledge_stage_input", default=None
)


def current_knowledge_stage_input() -> KnowledgeStageInput | None:
    return _current.get()


@contextmanager
def knowledge_stage_input(
    request: ProviderRequest, dependencies: tuple[SourceDependency, ...]
) -> Iterator[None]:
    token = _current.set(KnowledgeStageInput(request, dependencies))
    try:
        yield
    finally:
        _current.reset(token)
