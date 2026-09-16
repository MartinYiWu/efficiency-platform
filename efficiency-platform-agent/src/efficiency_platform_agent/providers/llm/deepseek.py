"""DeepSeek OpenAI 兼容模型适配器。

适配器只负责把厂商响应归一化为 S2 Provider 契约；客户端由组合根注入，
本模块不会创建客户端、读取配置或主动发起网络请求。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from ...core.ports import ModelProvider
from ...core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    JsonValue,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


def _json_value(value: JsonValue) -> Any:
    """将不可变 S2 JSON 值转换为 SDK 可消费的普通对象。"""
    if isinstance(value, JsonObject):
        return {key: _json_value(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _field(value: Any, name: str, default: Any = None) -> Any:
    """同时读取 SDK 对象和测试字典中的字段。"""
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage(raw: Any) -> ProviderUsage:
    """归一化 usage；缺省字段按未知零值处理，不伪造计数。"""
    usage = _field(raw, "usage")
    if usage is None:
        return ProviderUsage(0, 0, 0, 0, 0)
    prompt_details = _field(usage, "prompt_tokens_details")
    completion_details = _field(usage, "completion_tokens_details")
    cached = _field(prompt_details, "cached_tokens", 0)
    reasoning = _field(usage, "reasoning_tokens", None)
    if reasoning is None:
        reasoning = _field(completion_details, "reasoning_tokens", 0)
    return ProviderUsage(
        max(0, int(_field(usage, "prompt_tokens", 0) or 0)),
        max(0, int(_field(usage, "completion_tokens", 0) or 0)),
        max(0, int(cached or 0)),
        max(0, int(reasoning or 0)),
        0,
    )


class DeepSeekModelProvider(ModelProvider):
    """通过注入的 OpenAI 兼容客户端调用 DeepSeek。"""

    def __init__(self, client: Any, model: str, *, timeout_ms: int = 30_000) -> None:
        if client is None:
            raise ValueError("client不能为空")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model必须是非空字符串")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ValueError("timeout_ms必须为正整数")
        self.client = client
        self.model = model
        self.timeout_ms = timeout_ms
        self.descriptor = ExtensionDescriptor(
            name=f"deepseek.{model}",
            semantic_version="1.0.0",
            input_schema_version="s2.provider/1",
            output_schema_version="s2.provider/1",
            permissions=frozenset(),
            budget=ExecutionBudget(
                1, 0, 1_000_000, 1_000_000, timeout_ms, 1_000_000_000
            ),
            termination_conditions=frozenset({"provider_returned"}),
            checkpoint_version="s2.provider/1",
        )

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """执行一次非流式请求并返回 S2 结果；异常只保留安全错误信息。"""
        if not isinstance(request, ProviderRequest):
            raise TypeError("request必须是ProviderRequest")
        messages = tuple(
            {"role": item.role, "content": _json_value(item.content)}
            for item in request.messages
        )
        options = _json_value(request.options)
        if not isinstance(options, dict):
            options = {}
        options.pop("model", None)
        options["timeout"] = min(request.timeout_ms, self.timeout_ms) / 1000
        try:
            responses = getattr(self.client, "responses", None)
            if responses is not None and hasattr(responses, "create"):
                response = await responses.create(
                    model=self.model,
                    input=list(messages),
                    **options,
                )
            else:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=list(messages),
                    **options,
                )
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception as error:  # noqa: BLE001, 厂商异常不能越过 S2 边界
            status = _field(error, "status_code")
            if isinstance(status, int) and status == 401:
                code, retryable = "PROVIDER_AUTHENTICATION", False
            elif isinstance(status, int) and status == 429:
                code, retryable = "PROVIDER_RATE_LIMITED", True
            elif isinstance(status, int) and status >= 500:
                code, retryable = "PROVIDER_UPSTREAM", True
            elif isinstance(error, (TimeoutError, asyncio.TimeoutError)):
                code, retryable = "PROVIDER_TIMEOUT", True
            else:
                code, retryable = "PROVIDER_UNAVAILABLE", True
            return ProviderResult(
                request.contract_version,
                None,
                ProviderUsage(0, 0, 0, 0, 0),
                ProviderError(code, "provider", retryable, "DeepSeek 请求未完成"),
            )

        choices = _field(response, "choices", ())
        if choices:
            message = _field(choices[0], "message")
            content = _field(message, "content")
        else:
            content = _field(response, "output_text")
            if content is None:
                output = _field(response, "output", ())
                content = _field(output[0], "content") if output else None
        if content is None:
            return self._invalid_result(request, "DeepSeek 响应内容为空")
        try:
            normalized = ProviderMessage("assistant", content)
            return ProviderResult(
                request.contract_version, normalized, _usage(response)
            )
        except (TypeError, ValueError):
            return self._invalid_result(request, "DeepSeek 响应结构无效")

    @staticmethod
    def _invalid_result(request: ProviderRequest, message: str) -> ProviderResult:
        return ProviderResult(
            request.contract_version,
            None,
            ProviderUsage(0, 0, 0, 0, 0),
            ProviderError("PROVIDER_RESPONSE_INVALID", "provider", False, message),
        )

    async def close(self) -> None:
        """关闭注入客户端；没有 close 方法时保持幂等。"""
        close = getattr(self.client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result


__all__ = ["DeepSeekModelProvider"]
