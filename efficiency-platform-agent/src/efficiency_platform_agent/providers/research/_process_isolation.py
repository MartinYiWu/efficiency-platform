"""第三方内容解析器的可终止子进程隔离。"""

from __future__ import annotations

import multiprocessing
from collections.abc import Mapping
from multiprocessing.connection import Connection
from typing import Any, Literal, Protocol


class IsolatedParseTimeout(TimeoutError):
    pass


class IsolatedParseFailed(RuntimeError):
    pass


class _TerminableProcess(Protocol):
    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


def run_isolated_parser(
    operation: Literal["html", "feed"],
    payload: str | bytes,
    *,
    timeout_seconds: float,
) -> object:
    """执行固定解析操作；超时后终止并回收整个子进程。"""
    if timeout_seconds <= 0:
        raise ValueError("PARSE_TIMEOUT_INVALID")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_parse_worker,
        args=(child, operation, payload),
        daemon=True,
        name=f"research-{operation}-parser",
    )
    try:
        process.start()
        child.close()
        if not parent.poll(timeout_seconds):
            _stop_process(process)
            raise IsolatedParseTimeout("ISOLATED_PARSE_TIMEOUT")
        try:
            status, result = parent.recv()
        except EOFError as exc:
            raise IsolatedParseFailed("ISOLATED_PARSE_NO_RESULT") from exc
        if status != "ok":
            raise IsolatedParseFailed("ISOLATED_PARSE_FAILED")
        return result
    finally:
        parent.close()
        child.close()
        if process.is_alive():
            _stop_process(process)
        else:
            process.join(timeout=0.2)


def _stop_process(process: _TerminableProcess) -> None:
    if not process.is_alive():
        process.join(timeout=0.2)
        return
    process.terminate()
    process.join(timeout=1.0)
    if process.is_alive():
        process.kill()
        process.join(timeout=1.0)


def _parse_worker(
    connection: Connection,
    operation: Literal["html", "feed"],
    payload: str | bytes,
) -> None:
    try:
        if operation == "html" and isinstance(payload, str):
            import trafilatura  # type: ignore[import-not-found]

            result: object = trafilatura.extract(
                payload,
                include_comments=False,
                include_tables=False,
                include_links=False,
            )
        elif operation == "feed" and isinstance(payload, bytes):
            import feedparser  # type: ignore[import-not-found]

            result = _to_plain_value(feedparser.parse(payload))
        else:
            connection.send(("error", None))
            return
        connection.send(("ok", result))
    except Exception:  # noqa: BLE001 - 子进程边界只返回固定状态，不泄露解析器异常
        connection.send(("error", None))
    finally:
        connection.close()


def _to_plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_to_plain_value(item) for item in value)
    return value


__all__ = [
    "IsolatedParseFailed",
    "IsolatedParseTimeout",
    "run_isolated_parser",
]
