"""跨轮排名引用成稿的真实模型调用边界。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from efficiency_platform_agent.core.run import ProviderMessage

logger = logging.getLogger(__name__)


class ReferencedContentModelRuntime:
    """不生成本地草稿，只为带引用的真实模型调用补充安全日志。"""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    async def complete(self, demand, request, **kwargs):
        raw = _request_payload(request.messages)
        referenced = bool(
            isinstance(raw, dict)
            and isinstance(raw.get("input_deliverables"), list)
            and raw["input_deliverables"]
        )
        started = time.monotonic()
        if referenced:
            logger.info(
                "event=referenced_content_model_started platform=%s input_count=%s",
                raw.get("platform"),
                len(raw["input_deliverables"]),
            )
        try:
            execution = await self.delegate.complete(demand, request, **kwargs)
        except Exception as exc:
            if referenced:
                logger.exception(
                    "event=referenced_content_model_failed platform=%s elapsed_ms=%s exception_type=%s",
                    raw.get("platform"),
                    int((time.monotonic() - started) * 1000),
                    type(exc).__name__,
                )
            raise
        if referenced:
            error = getattr(getattr(execution, "result", None), "error", None)
            logger.log(
                logging.WARNING if error is not None else logging.INFO,
                "event=referenced_content_model_%s platform=%s elapsed_ms=%s provider_error=%s",
                "failed" if error is not None else "succeeded",
                raw.get("platform"),
                int((time.monotonic() - started) * 1000),
                getattr(error, "code", None),
            )
        return execution


def _request_payload(messages: tuple[ProviderMessage, ...]) -> dict[str, Any] | None:
    if not messages:
        return None
    content = messages[-1].content
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


__all__ = ["ReferencedContentModelRuntime"]
