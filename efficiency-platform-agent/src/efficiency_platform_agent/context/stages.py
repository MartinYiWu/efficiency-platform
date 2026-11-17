"""业务逻辑阶段绑定；有限修复沿用原输入和固定阶段身份。"""

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from functools import wraps
from hashlib import sha256
from typing import Any, TypeVar, cast

from efficiency_platform_agent.core.context_dispatch import model_stage

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _json(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("CONTEXT_STAGE_INPUT_UNSUPPORTED")


def stage_entry(
    name: str,
    *,
    inputs: tuple[str, ...],
    identity: tuple[str, ...] = (),
    node_fields: tuple[str, ...] = (),
    subtask_field: str | None = None,
) -> Callable[[F], F]:
    def decorate(function: F) -> F:
        signature = inspect.signature(function)

        @wraps(function)
        async def invoke(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()

            def read(path: str) -> Any:
                head, *tail = path.split(".")
                value = bound.arguments[head]
                for field in tail:
                    value = getattr(value, field)
                return value

            identity_json = json.dumps(
                [name, *(read(key) for key in identity)],
                default=_json,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            semantic = json.dumps(
                {key: read(key) for key in inputs},
                default=_json,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
            node_id = ":".join((name, *(str(read(key)) for key in node_fields)))
            with model_stage(
                sha256(identity_json.encode()).hexdigest(),
                semantic,
                node_id=node_id,
                subtask_id=read(subtask_field) if subtask_field else None,
            ) as stage:
                value = await function(*args, **kwargs)
                if stage.complete is not None:
                    await stage.complete()
                return value

        return cast(F, invoke)

    return decorate
