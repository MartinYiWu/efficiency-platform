"""有界解析厂商用量，不记录回答正文；未知或矛盾数据不得退款。"""

from __future__ import annotations

import json
import zlib
from typing import Any

from ..core.paid_budget import PaidBudgetError, PaidUsage


def input_token_upper_bound(provider: str, body: bytes, payload: dict[str, Any]) -> int:
    # 整个JSON按每UTF-8字节最多一个token计，再为消息及厂商封装留保守余量。
    bound = len(body) + 4096
    if provider == "deepseek":
        bound += 256 * len(payload.get("messages", []))
    elif provider == "embedding":
        values = payload.get("input", [])
        bound += 256 * (len(values) if isinstance(values, list) else 1)
    elif provider == "rerank":
        value = payload.get("input", {})
        query, documents = value.get("query"), value.get("documents")
        if (
            not isinstance(query, str)
            or not isinstance(documents, list)
            or not all(isinstance(item, str) for item in documents)
        ):
            raise PaidBudgetError("PAID_INPUT_BOUND_REQUIRED", "重排输入无法确定上界")
        bound += len(documents) * (len(query.encode("utf-8")) + 512)
    else:
        raise PaidBudgetError("UNKNOWN_PRICE", "未知付费能力")
    return bound


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError
    return value


class _MissingReasoningUsage(ValueError):
    """总量字段合法，但缺少启用思考模式所需的推理用量。"""


def _usage(provider: str, value: Any, thinking: bool) -> PaidUsage:
    if not isinstance(value, dict):
        raise TypeError
    if provider in {"embedding", "rerank"}:
        tokens = value.get(
            "input_tokens", value.get("prompt_tokens", value.get("total_tokens"))
        )
        result = PaidUsage(_integer(tokens), 0)
        for name in ("input_tokens", "prompt_tokens", "total_tokens"):
            if name in value and _integer(value[name]) != result.input_tokens:
                raise ValueError
        return result
    input_tokens = _integer(value["prompt_tokens"])
    output_tokens = _integer(value["completion_tokens"])
    cached = value.get(
        "prompt_cache_hit_tokens",
        value.get("prompt_tokens_details", {}).get("cached_tokens", 0),
    )
    if (
        "prompt_cache_hit_tokens" in value
        and "cached_tokens" in value.get("prompt_tokens_details", {})
        and _integer(value["prompt_cache_hit_tokens"])
        != _integer(value["prompt_tokens_details"]["cached_tokens"])
    ):
        raise ValueError
    details = value.get("completion_tokens_details", {})
    if (
        "prompt_cache_miss_tokens" in value
        and _integer(cached) + _integer(value["prompt_cache_miss_tokens"])
        != input_tokens
    ):
        raise ValueError
    reasoning = details.get("reasoning_tokens", value.get("reasoning_tokens"))
    if (
        "reasoning_tokens" in details
        and "reasoning_tokens" in value
        and _integer(details["reasoning_tokens"]) != _integer(value["reasoning_tokens"])
    ):
        raise ValueError
    if reasoning is None:
        if thinking:
            raise _MissingReasoningUsage
        reasoning = 0
    result = PaidUsage(
        input_tokens, output_tokens, _integer(cached), _integer(reasoning)
    )
    if (
        "total_tokens" in value
        and _integer(value["total_tokens"]) != input_tokens + output_tokens
    ):
        raise ValueError
    return result


class PaidUsageCollector:
    """只在正常读完及终态可证实时公开usage；内存有界。"""

    def __init__(
        self,
        provider: str,
        content_type: str,
        *,
        thinking: bool = False,
        content_encoding: str = "",
    ) -> None:
        self.provider = provider
        self.sse = "text/event-stream" in content_type.lower()
        self.thinking = thinking
        self.buffer = b""
        self.candidate: PaidUsage | None = None
        self.usage: PaidUsage | None = None
        encoding = content_encoding.strip().lower()
        self.invalid = encoding not in {"", "identity", "gzip", "deflate"}
        self.encoding = (encoding or "identity") if not self.invalid else "unsupported"
        self.failure_reason = "UNSUPPORTED_ENCODING" if self.invalid else ""
        self.usage_seen = False
        self.reasoning_usage_seen = False
        self._decoder = (
            zlib.decompressobj(
                16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
            )
            if encoding in {"gzip", "deflate"}
            else None
        )
        self._decoded_bytes = 0
        # SSE允许持续消费多个缓冲区，但累计解压仍须有上限。
        self._decoded_limit = 8 * 1024 * 1024 if self.sse else 262144
        self.done = False
        self.terminal = False

    def _fail(self, reason: str) -> None:
        self.failure_reason = self.failure_reason or reason
        self.invalid = True
        self.buffer = b""

    def diagnostics(self) -> dict[str, str | bool]:
        """只公开固定原因及布尔状态，不带正文、头值或厂商自定义字段。"""
        reason = self.failure_reason
        if not reason:
            if self.usage is not None:
                reason = "VALID_USAGE"
            elif not self.done:
                reason = "MISSING_DONE"
            elif not self.terminal:
                reason = "MISSING_TERMINAL"
            elif self.candidate is None:
                reason = "MISSING_USAGE"
            else:
                reason = "AWAITING_EOF"
        return {
            "reason": reason,
            "encoding": self.encoding,
            "sse": self.sse,
            "done": self.done,
            "terminal": self.terminal,
            "invalid": self.invalid,
            "usage_seen": self.usage_seen,
            "reasoning_usage_seen": self.reasoning_usage_seen,
        }

    def feed(self, chunk: bytes) -> None:
        if self.invalid:
            return
        if self._decoder is not None:
            try:
                # 多成员、尾随数据和超限解压均不能证明完整用量。
                while True:
                    decoded = self._decoder.decompress(
                        chunk,
                        min(
                            16384,
                            self._decoded_limit + 1 - self._decoded_bytes,
                            max(1, 262144 - len(self.buffer)),
                        ),
                    )
                    self._decoded_bytes += len(decoded)
                    if self._decoded_bytes > self._decoded_limit:
                        self._fail("RESPONSE_LIMIT_EXCEEDED")
                        return
                    if self._decoder.unused_data:
                        self._fail("INVALID_COMPRESSION")
                        return
                    self._feed_decoded(decoded)
                    if self.invalid:
                        return
                    chunk = self._decoder.unconsumed_tail
                    if not chunk:
                        return
            except (ValueError, zlib.error):
                self._fail("INVALID_COMPRESSION")
                return
        self._feed_decoded(chunk)

    def _feed_decoded(self, chunk: bytes) -> None:
        self.buffer += chunk
        if len(self.buffer) > 262144:
            self._fail("RESPONSE_LIMIT_EXCEEDED")
            return
        if not self.sse:
            return
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.rstrip(b"\r")
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if raw == b"[DONE]":
                self.done = True
                continue
            if self.done:
                self._fail("EVENT_AFTER_DONE")
                return
            try:
                self._value(json.loads(raw))
            except (ValueError, KeyError, TypeError, AttributeError, PaidBudgetError):
                self._fail("INVALID_EVENT")
                return

    def _value(self, value: Any) -> None:
        if not isinstance(value, dict) or value.get("error"):
            raise ValueError
        if self.provider == "deepseek":
            for choice in value.get("choices", []):
                if choice.get("finish_reason") in {"stop", "length", "tool_calls"}:
                    self.terminal = True
        elif self.provider == "embedding":
            self.terminal = isinstance(value.get("data"), list)
        elif self.provider == "rerank":
            self.terminal = isinstance(value.get("output", {}).get("results"), list)
        if value.get("usage") is not None:
            self.usage_seen = True
            raw = value["usage"]
            details = (
                raw.get("completion_tokens_details") if isinstance(raw, dict) else None
            )
            reasoning = (
                details.get("reasoning_tokens") if isinstance(details, dict) else None
            )
            if reasoning is None and isinstance(raw, dict):
                reasoning = raw.get("reasoning_tokens")
            self.reasoning_usage_seen = (
                self.reasoning_usage_seen or reasoning is not None
            )
            try:
                candidate = _usage(self.provider, raw, self.thinking)
            except (
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                PaidBudgetError,
            ) as error:
                self._fail(
                    "MISSING_REASONING_USAGE"
                    if isinstance(error, _MissingReasoningUsage)
                    else "INVALID_USAGE"
                )
                raise
            if self.candidate is not None and self.candidate != candidate:
                self._fail("CONFLICTING_USAGE")
                raise ValueError
            self.candidate = candidate

    def end(self) -> None:
        if self.invalid:
            return
        try:
            if self._decoder is not None and not self._decoder.eof:
                self._fail("INCOMPLETE_COMPRESSION")
                raise ValueError
            if not self.sse:
                self._value(json.loads(self.buffer))
                self.done = True
            elif self.buffer.strip():
                self._fail("INCOMPLETE_SSE")
                raise ValueError
            if self.done and self.terminal:
                self.usage = self.candidate
        except (ValueError, KeyError, TypeError, AttributeError, PaidBudgetError):
            self._fail("INVALID_EVENT")
        finally:
            self.buffer = b""
