"""DeepSeek OpenAI 兼容接口的流式 Provider。

本模块只依赖注入的 HTTP 客户端，不读取环境变量，也不记录请求正文或密钥。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from types import MappingProxyType
from typing import Any

import httpx

from ..core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    safe_exception_location,
)
from ..core.ports import ModelProvider, StreamingModelProvider
from ..core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    JsonValue,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
    ProviderToolCall,
    ProviderUsage,
)
from .json_schema import request_json_schema, validate_json_response


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _json_value(value: JsonValue) -> Any:
    """递归把 Agent 不可变 JSON 值转换为标准 JSON 对象。"""
    if isinstance(value, JsonObject):
        return {key: _json_value(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _usage(value: Any) -> ProviderUsage:
    raw = _field(value, "usage") or value
    prompt_details = _field(raw, "prompt_tokens_details") or {}
    completion_details = _field(raw, "completion_tokens_details") or {}
    return ProviderUsage(
        max(0, int(_field(raw, "prompt_tokens", 0) or 0)),
        max(0, int(_field(raw, "completion_tokens", 0) or 0)),
        max(
            0,
            int(
                _field(raw, "prompt_cache_hit_tokens", 0)
                or _field(prompt_details, "cached_tokens", 0)
                or 0
            ),
        ),
        max(0, int(_field(completion_details, "reasoning_tokens", 0) or 0)),
        0,
    )


def _serialize_message(
    message: ProviderMessage, *, supports_developer_role: bool
) -> dict[str, Any]:
    role = message.role
    content = _json_value(message.content)
    if role == "developer" and not supports_developer_role:
        role = "system"
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, sort_keys=True)
        content = f"[DEVELOPER INSTRUCTION]\n{content}"
    payload: dict[str, Any] = {"role": role, "content": content}
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.tool_call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        _json_value(call.arguments),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in message.tool_calls
        ]
    return payload


def _freeze_json(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, Mapping):
        return JsonObject(
            tuple((str(key), _freeze_json(item)) for key, item in value.items())
        )
    raise ValueError("tool arguments are not JSON")


def _finalize_tool_calls(
    parts: Mapping[int, Mapping[str, str]],
) -> tuple[ProviderToolCall, ...]:
    calls: list[ProviderToolCall] = []
    for index in sorted(parts):
        part = parts[index]
        arguments = json.loads(part.get("arguments", "{}"))
        frozen = _freeze_json(arguments)
        if not isinstance(frozen, JsonObject):
            raise TypeError("tool arguments must be an object")
        calls.append(
            ProviderToolCall(
                part.get("id", ""),
                part.get("name", ""),
                frozen,
            )
        )
    return tuple(calls)


def _error(
    code: str, category: str, message: str, retryable: bool
) -> ProviderStreamChunk:
    return ProviderStreamChunk(error=ProviderError(code, category, retryable, message))


class DeepSeekStreamingProvider(ModelProvider, StreamingModelProvider):
    """把 DeepSeek SSE 增量转换为 Agent 自有流式事件。"""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        timeout_ms: int = 30_000,
        max_retries: int = 1,
        cancellation_signal: Any | None = None,
        owns_client: bool = False,
        logical_model_map: Mapping[str, str] | None = None,
        diagnostic_recorder: DiagnosticRecorderPort | None = None,
        supports_developer_role: bool = False,
    ) -> None:
        if client is None:
            raise ValueError("client不能为空")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model必须是非空字符串")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key必须是非空字符串")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url必须是非空字符串")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ValueError("timeout_ms必须为正整数")
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 3:
            raise ValueError("max_retries必须在0到3之间")
        self.client = client
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.cancellation_signal = cancellation_signal
        self.owns_client = owns_client
        self.diagnostic_recorder = diagnostic_recorder or NoopDiagnosticRecorder()
        self.supports_developer_role = supports_developer_role
        normalized_models = dict(logical_model_map or {})
        if any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in normalized_models.items()
        ):
            raise ValueError("logical_model_map必须是非空字符串映射")
        self.logical_model_map = MappingProxyType(normalized_models)
        self.descriptor = ExtensionDescriptor(
            name=f"deepseek.{model}",
            semantic_version="1.0.0",
            input_schema_version="s2.provider/1",
            output_schema_version="s2.provider/1",
            permissions=frozenset(),
            budget=ExecutionBudget(
                2, 0, 1_000_000, 1_000_000, timeout_ms, 1_000_000_000
            ),
            termination_conditions=frozenset({"provider_returned", "provider_error"}),
            checkpoint_version="s2.provider/1",
        )

    async def _cancel_requested(self) -> bool:
        """读取同步或异步取消信号，避免把取消当作普通错误。"""
        signal = self.cancellation_signal
        if signal is None:
            return False
        probe = getattr(signal, "wait_requested", signal)
        value = probe() if callable(probe) else probe
        if hasattr(value, "__await__"):
            value = await value
        return bool(value)

    def _record_provider_attempt(
        self,
        event_name: str,
        level: DiagnosticLevel,
        *,
        selected_model: str,
        provider_call_id: str,
        attempt: int,
        started_at_ns: int,
        error_code: str | None = None,
        error_type: str | None = None,
        http_status: int | None = None,
        retryable: bool | None = None,
        error: BaseException | None = None,
    ) -> None:
        """记录单次 HTTP 尝试的固定事实，不读取请求或异常正文。"""

        try:
            self.diagnostic_recorder.record(
                DiagnosticRecord(
                    event_name=event_name,
                    component="provider",
                    level=level,
                    capability="deepseek_chat",
                    stage="chat.completions.stream",
                    provider="deepseek",
                    model=selected_model,
                    provider_call_id=provider_call_id,
                    error_code=error_code,
                    error_type=error_type,
                    error_location=(
                        safe_exception_location(error) if error is not None else None
                    ),
                    http_status=http_status,
                    retryable=retryable,
                    duration_ms=max(
                        0, (time.monotonic_ns() - started_at_ns) // 1_000_000
                    ),
                    attempt=attempt,
                )
            )
        except Exception:  # noqa: BLE001 - Recorder 异常不得改变 Provider 语义
            return

    async def stream(
        self, request: ProviderRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        """请求并解析 SSE；认证、限流、超时和上游错误不泄露厂商异常。"""
        if not isinstance(request, ProviderRequest):
            raise TypeError("request必须是ProviderRequest")
        messages = [
            _serialize_message(
                message,
                supports_developer_role=self.supports_developer_role,
            )
            for message in request.messages
        ]
        options = _json_value(request.options)
        if not isinstance(options, dict):
            options = {}
        logical_model = options.get("logical_model")
        for reserved in (
            "logical_model",
            "json_schema",
            "model",
            "messages",
            "stream",
            "base_url",
            "api_key",
        ):
            options.pop(reserved, None)
        if logical_model is not None and not isinstance(logical_model, str):
            yield _error("PROVIDER_MODEL_INVALID", "provider", "逻辑模型无效", False)
            return
        if self.logical_model_map:
            if (
                logical_model is not None
                and logical_model not in self.logical_model_map
            ):
                yield _error(
                    "PROVIDER_MODEL_INVALID", "provider", "逻辑模型不可用", False
                )
                return
            selected_model = (
                self.model
                if logical_model is None
                else self.logical_model_map[logical_model]
            )
        else:
            selected_model = self.model
            if logical_model is not None and logical_model != self.model:
                yield _error(
                    "PROVIDER_MODEL_INVALID", "provider", "逻辑模型不可用", False
                )
                return
        if "response_format" in options:
            options["response_format"] = {"type": "json_object"}
        payload = {
            "model": selected_model,
            "messages": messages,
            **options,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = min(request.timeout_ms, self.timeout_ms) / 1000
        attempts = 0
        while True:
            emitted = False
            first_sse_event_recorded = False
            first_reasoning_recorded = False
            first_content_recorded = False
            tool_call_parts: dict[int, dict[str, str]] = {}
            if await self._cancel_requested():
                raise asyncio.CancelledError
            attempt_number = attempts + 1
            provider_call_id = f"model-http-{uuid.uuid4().hex}"
            started_at_ns = time.monotonic_ns()
            self._record_provider_attempt(
                "provider_request_started",
                DiagnosticLevel.INFO,
                selected_model=selected_model,
                provider_call_id=provider_call_id,
                attempt=attempt_number,
                started_at_ns=started_at_ns,
            )
            try:
                async with asyncio.timeout(timeout):
                    stream_context = self.client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    )
                    async with stream_context as response:
                        status = int(getattr(response, "status_code", 200))
                        self._record_provider_attempt(
                            "provider_response_headers_received",
                            DiagnosticLevel.INFO,
                            selected_model=selected_model,
                            provider_call_id=provider_call_id,
                            attempt=attempt_number,
                            started_at_ns=started_at_ns,
                            http_status=status,
                        )
                        if status == 401:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_AUTHENTICATION",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_AUTHENTICATION",
                                "authentication",
                                "DeepSeek 认证失败",
                                False,
                            )
                            return
                        if status == 429:
                            if attempts < self.max_retries:
                                self._record_provider_attempt(
                                    "provider_request_retrying",
                                    DiagnosticLevel.WARNING,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    error_code="PROVIDER_RATE_LIMIT",
                                    error_type="HTTPStatusError",
                                    http_status=status,
                                    retryable=True,
                                )
                                attempts += 1
                                await self._backoff(attempts)
                                continue
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_RATE_LIMIT",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=True,
                            )
                            yield _error(
                                "PROVIDER_RATE_LIMIT",
                                "rate_limit",
                                "DeepSeek 请求受限",
                                True,
                            )
                            return
                        if status == 408:
                            if attempts < self.max_retries:
                                self._record_provider_attempt(
                                    "provider_request_retrying",
                                    DiagnosticLevel.WARNING,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    error_code="PROVIDER_TIMEOUT",
                                    error_type="HTTPStatusError",
                                    http_status=status,
                                    retryable=True,
                                )
                                attempts += 1
                                await self._backoff(attempts)
                                continue
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_TIMEOUT",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=True,
                            )
                            yield _error(
                                "PROVIDER_TIMEOUT", "timeout", "DeepSeek 请求超时", True
                            )
                            return
                        if status >= 500:
                            if attempts < self.max_retries:
                                self._record_provider_attempt(
                                    "provider_request_retrying",
                                    DiagnosticLevel.WARNING,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    error_code="PROVIDER_SERVER_ERROR",
                                    error_type="HTTPStatusError",
                                    http_status=status,
                                    retryable=True,
                                )
                                attempts += 1
                                await self._backoff(attempts)
                                continue
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_SERVER_ERROR",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=True,
                            )
                            yield _error(
                                "PROVIDER_SERVER_ERROR",
                                "server_error",
                                "DeepSeek 服务暂不可用",
                                True,
                            )
                            return
                        if status in {400, 422}:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_INVALID_REQUEST",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_INVALID_REQUEST",
                                "provider",
                                "DeepSeek 请求参数无效",
                                False,
                            )
                            return
                        if status == 401 or status == 403:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_AUTHENTICATION",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_AUTHENTICATION",
                                "authentication",
                                "DeepSeek 认证失败",
                                False,
                            )
                            return
                        if status == 404:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_NOT_FOUND",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_NOT_FOUND",
                                "provider",
                                "DeepSeek 接口不存在",
                                False,
                            )
                            return
                        if status == 409:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_CONFLICT",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_CONFLICT",
                                "provider",
                                "DeepSeek 请求冲突",
                                False,
                            )
                            return
                        if status >= 400:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_UNAVAILABLE",
                                error_type="HTTPStatusError",
                                http_status=status,
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_UNAVAILABLE",
                                "provider",
                                "DeepSeek 请求未完成",
                                False,
                            )
                            return
                        terminated = False
                        async for line in response.aiter_lines():
                            if await self._cancel_requested():
                                raise asyncio.CancelledError
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not first_sse_event_recorded:
                                self._record_provider_attempt(
                                    "provider_first_sse_event_received",
                                    DiagnosticLevel.INFO,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    http_status=status,
                                )
                                first_sse_event_recorded = True
                            if raw == "[DONE]":
                                terminated = True
                                self._record_provider_attempt(
                                    "provider_request_succeeded",
                                    DiagnosticLevel.INFO,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                )
                                return
                            try:
                                event = json.loads(raw)
                            except (TypeError, ValueError):
                                self._record_provider_attempt(
                                    "provider_request_failed",
                                    DiagnosticLevel.ERROR,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    error_code="PROVIDER_RESPONSE_INVALID",
                                    error_type="ResponseDecodeError",
                                    retryable=False,
                                )
                                yield _error(
                                    "PROVIDER_RESPONSE_INVALID",
                                    "provider",
                                    "DeepSeek 流响应格式无效",
                                    False,
                                )
                                return
                            choices = _field(event, "choices", ()) or ()
                            choice = choices[0] if choices else None
                            delta_object = _field(choice, "delta", {})
                            reasoning_delta = (
                                _field(
                                    delta_object,
                                    "reasoning_content",
                                    "",
                                )
                                or ""
                            )
                            if reasoning_delta and not first_reasoning_recorded:
                                self._record_provider_attempt(
                                    "provider_first_reasoning_received",
                                    DiagnosticLevel.INFO,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    http_status=status,
                                )
                                first_reasoning_recorded = True
                            delta = _field(delta_object, "content", "") or ""
                            raw_tool_calls = _field(delta_object, "tool_calls", ()) or ()
                            for raw_call in raw_tool_calls:
                                index = int(_field(raw_call, "index", 0) or 0)
                                current = tool_call_parts.setdefault(
                                    index, {"id": "", "name": "", "arguments": ""}
                                )
                                call_id = _field(raw_call, "id")
                                if call_id:
                                    current["id"] = str(call_id)
                                function = _field(raw_call, "function", {}) or {}
                                name = _field(function, "name")
                                if name:
                                    current["name"] += str(name)
                                arguments = _field(function, "arguments")
                                if arguments:
                                    current["arguments"] += str(arguments)
                            if delta and not first_content_recorded:
                                self._record_provider_attempt(
                                    "provider_first_content_received",
                                    DiagnosticLevel.INFO,
                                    selected_model=selected_model,
                                    provider_call_id=provider_call_id,
                                    attempt=attempt_number,
                                    started_at_ns=started_at_ns,
                                    http_status=status,
                                )
                                first_content_recorded = True
                            finish_reason = _field(choice, "finish_reason")
                            usage = (
                                _usage(event)
                                if _field(event, "usage") is not None
                                else ProviderUsage(0, 0, 0, 0, 0)
                            )
                            tool_calls: tuple[ProviderToolCall, ...] = ()
                            if finish_reason is not None and tool_call_parts:
                                try:
                                    tool_calls = _finalize_tool_calls(tool_call_parts)
                                except (TypeError, ValueError):
                                    self._record_provider_attempt(
                                        "provider_request_failed",
                                        DiagnosticLevel.ERROR,
                                        selected_model=selected_model,
                                        provider_call_id=provider_call_id,
                                        attempt=attempt_number,
                                        started_at_ns=started_at_ns,
                                        error_code="PROVIDER_TOOL_CALL_INVALID",
                                        error_type="ToolCallDecodeError",
                                        retryable=False,
                                    )
                                    yield _error(
                                        "PROVIDER_TOOL_CALL_INVALID",
                                        "provider",
                                        "DeepSeek Tool Call 格式无效",
                                        False,
                                    )
                                    return
                            emitted = (
                                emitted
                                or bool(delta)
                                or bool(raw_tool_calls)
                                or finish_reason is not None
                                or usage != ProviderUsage(0, 0, 0, 0, 0)
                            )
                            yield ProviderStreamChunk(
                                str(delta),
                                usage,
                                finish_reason,
                                tool_calls=tool_calls,
                            )
                            if finish_reason is not None:
                                terminated = True
                        if not terminated:
                            self._record_provider_attempt(
                                "provider_request_failed",
                                DiagnosticLevel.ERROR,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                                error_code="PROVIDER_RESPONSE_TRUNCATED",
                                error_type="ResponseTruncated",
                                retryable=False,
                            )
                            yield _error(
                                "PROVIDER_RESPONSE_TRUNCATED",
                                "provider",
                                "DeepSeek 流响应未正常结束",
                                False,
                            )
                        else:
                            self._record_provider_attempt(
                                "provider_request_succeeded",
                                DiagnosticLevel.INFO,
                                selected_model=selected_model,
                                provider_call_id=provider_call_id,
                                attempt=attempt_number,
                                started_at_ns=started_at_ns,
                            )
                return
            except asyncio.CancelledError as error:
                self._record_provider_attempt(
                    "provider_request_cancelled",
                    DiagnosticLevel.WARNING,
                    selected_model=selected_model,
                    provider_call_id=provider_call_id,
                    attempt=attempt_number,
                    started_at_ns=started_at_ns,
                    error_code="CANCELLED",
                    error_type=type(error).__name__,
                    retryable=False,
                    error=error,
                )
                raise
            except TimeoutError as error:
                if not emitted and attempts < self.max_retries:
                    self._record_provider_attempt(
                        "provider_request_retrying",
                        DiagnosticLevel.WARNING,
                        selected_model=selected_model,
                        provider_call_id=provider_call_id,
                        attempt=attempt_number,
                        started_at_ns=started_at_ns,
                        error_code="PROVIDER_TIMEOUT",
                        error_type=type(error).__name__,
                        retryable=True,
                        error=error,
                    )
                    attempts += 1
                    await self._backoff(attempts)
                    continue
                self._record_provider_attempt(
                    "provider_request_failed",
                    DiagnosticLevel.ERROR,
                    selected_model=selected_model,
                    provider_call_id=provider_call_id,
                    attempt=attempt_number,
                    started_at_ns=started_at_ns,
                    error_code="PROVIDER_TIMEOUT",
                    error_type=type(error).__name__,
                    retryable=True,
                    error=error,
                )
                yield _error("PROVIDER_TIMEOUT", "timeout", "DeepSeek 请求超时", True)
                return
            except httpx.TimeoutException as error:
                if isinstance(error, httpx.ConnectTimeout):
                    timeout_code = "PROVIDER_CONNECT_TIMEOUT"
                    timeout_message = "DeepSeek 建立连接超时"
                elif isinstance(error, httpx.ReadTimeout):
                    timeout_code = "PROVIDER_READ_TIMEOUT"
                    timeout_message = "DeepSeek 读取响应超时"
                else:
                    timeout_code = "PROVIDER_TIMEOUT"
                    timeout_message = "DeepSeek 请求超时"
                if not emitted and attempts < self.max_retries:
                    self._record_provider_attempt(
                        "provider_request_retrying",
                        DiagnosticLevel.WARNING,
                        selected_model=selected_model,
                        provider_call_id=provider_call_id,
                        attempt=attempt_number,
                        started_at_ns=started_at_ns,
                        error_code=timeout_code,
                        error_type=type(error).__name__,
                        retryable=True,
                        error=error,
                    )
                    attempts += 1
                    await self._backoff(attempts)
                    continue
                self._record_provider_attempt(
                    "provider_request_failed",
                    DiagnosticLevel.ERROR,
                    selected_model=selected_model,
                    provider_call_id=provider_call_id,
                    attempt=attempt_number,
                    started_at_ns=started_at_ns,
                    error_code=timeout_code,
                    error_type=type(error).__name__,
                    retryable=True,
                    error=error,
                )
                yield _error(timeout_code, "timeout", timeout_message, True)
                return
            except httpx.TransportError as error:
                if not emitted and attempts < self.max_retries:
                    self._record_provider_attempt(
                        "provider_request_retrying",
                        DiagnosticLevel.WARNING,
                        selected_model=selected_model,
                        provider_call_id=provider_call_id,
                        attempt=attempt_number,
                        started_at_ns=started_at_ns,
                        error_code="PROVIDER_CONNECTION",
                        error_type=type(error).__name__,
                        retryable=True,
                        error=error,
                    )
                    attempts += 1
                    await self._backoff(attempts)
                    continue
                self._record_provider_attempt(
                    "provider_request_failed",
                    DiagnosticLevel.ERROR,
                    selected_model=selected_model,
                    provider_call_id=provider_call_id,
                    attempt=attempt_number,
                    started_at_ns=started_at_ns,
                    error_code="PROVIDER_CONNECTION",
                    error_type=type(error).__name__,
                    retryable=True,
                    error=error,
                )
                yield _error(
                    "PROVIDER_CONNECTION", "connection", "DeepSeek 网络连接失败", True
                )
                return
            except httpx.HTTPError as error:
                self._record_provider_attempt(
                    "provider_request_failed",
                    DiagnosticLevel.ERROR,
                    selected_model=selected_model,
                    provider_call_id=provider_call_id,
                    attempt=attempt_number,
                    started_at_ns=started_at_ns,
                    error_code="PROVIDER_UNAVAILABLE",
                    error_type=type(error).__name__,
                    retryable=False,
                    error=error,
                )
                yield _error(
                    "PROVIDER_UNAVAILABLE", "provider", "DeepSeek 请求未完成", False
                )
                return

    async def close(self) -> None:
        """关闭注入客户端；关闭动作本身不暴露厂商错误。"""
        if not self.owns_client:
            return
        close = getattr(self.client, "aclose", None) or getattr(
            self.client, "close", None
        )
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """通过同一流式适配器提供 ModelProvider 非流式兼容能力。"""
        total = ProviderUsage(0, 0, 0, 0, 0)
        for attempt in range(self.max_retries + 1):
            result = await self._complete_once(request)
            total = ProviderUsage(
                total.input_tokens + result.usage.input_tokens,
                total.output_tokens + result.usage.output_tokens,
                total.cached_tokens + result.usage.cached_tokens,
                total.reasoning_tokens + result.usage.reasoning_tokens,
                total.cost_microunits + result.usage.cost_microunits,
            )
            response_error = result.error
            retry_empty = (
                response_error is not None
                and response_error.code == "PROVIDER_RESPONSE_INVALID"
                and response_error.retryable
                and attempt < self.max_retries
            )
            if retry_empty:
                assert response_error is not None
                try:
                    self.diagnostic_recorder.record(
                        DiagnosticRecord(
                            event_name="provider_empty_response_retrying",
                            component="provider",
                            level=DiagnosticLevel.WARNING,
                            capability="deepseek_chat",
                            stage="chat.completions.stream",
                            provider="deepseek",
                            error_code=response_error.code,
                            retryable=True,
                            attempt=attempt + 1,
                        )
                    )
                except Exception:  # noqa: BLE001, S110 - 诊断失败不得改变语义
                    pass
                await self._backoff(attempt + 1)
                continue
            return ProviderResult(
                request.contract_version,
                result.message,
                total,
                result.error,
            )
        raise AssertionError("unreachable")

    async def _complete_once(self, request: ProviderRequest) -> ProviderResult:
        """收集一次完整流；重试只由 complete 的有界循环触发。"""
        parts: list[str] = []
        total = ProviderUsage(0, 0, 0, 0, 0)
        finish = False
        tool_calls: tuple[ProviderToolCall, ...] = ()
        async for chunk in self.stream(request):
            if chunk.error is not None:
                return ProviderResult(
                    request.contract_version, None, total, chunk.error
                )
            parts.append(chunk.delta)
            usage = chunk.usage
            total = ProviderUsage(
                max(total.input_tokens, usage.input_tokens),
                max(total.output_tokens, usage.output_tokens),
                max(total.cached_tokens, usage.cached_tokens),
                max(total.reasoning_tokens, usage.reasoning_tokens),
                0,
            )
            finish = finish or chunk.finish_reason is not None
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls
        if not finish:
            return ProviderResult(
                request.contract_version,
                None,
                total,
                ProviderError(
                    "PROVIDER_RESPONSE_TRUNCATED",
                    "provider",
                    False,
                    "DeepSeek 流响应未正常结束",
                ),
            )
        content = "".join(parts)
        if not content and not tool_calls:
            return ProviderResult(
                request.contract_version,
                None,
                total,
                ProviderError(
                    "PROVIDER_RESPONSE_INVALID",
                    "provider",
                    True,
                    "DeepSeek 响应内容为空",
                ),
            )
        if not tool_calls:
            try:
                schema = request_json_schema(request.options)
                if schema is not None:
                    validate_json_response(content, schema)
            except (TypeError, ValueError):
                return ProviderResult(
                    request.contract_version,
                    None,
                    total,
                    ProviderError(
                        "PROVIDER_SCHEMA_INVALID",
                        "provider",
                        False,
                        "DeepSeek 响应不符合输出契约",
                    ),
                )
        return ProviderResult(
            request.contract_version,
            ProviderMessage(
                "assistant",
                content or None,
                tool_calls=tool_calls,
            ),
            total,
        )

    async def _backoff(self, attempt: int) -> None:
        """执行有界指数退避，避免重试风暴。"""
        await asyncio.sleep(min(0.05 * (2 ** max(0, attempt - 1)), 0.2))


__all__ = [
    "DeepSeekStreamingProvider",
    "ProviderError",
    "ProviderStreamChunk",
    "StreamingModelProvider",
]
