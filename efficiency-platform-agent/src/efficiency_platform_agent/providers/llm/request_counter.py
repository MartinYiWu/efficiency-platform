"""已准入文本序列化的保守计数；不读取密钥、不下载分词器、不调用计数服务。"""

from __future__ import annotations

import json

from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.paid_usage import input_token_upper_bound

from .deepseek import _json_value, _serialize_message


class ContextCapacityError(ValueError):
    """不回显输入内容或模型配置的安全计数错误。"""

    code = "CONTEXT_CAPACITY_UNVERIFIED"

    def __init__(self) -> None:
        super().__init__("模型容量或请求计数方式尚未核实，未发送请求")


class ConservativeRequestTokenCounter:
    """复用现有传输上界，覆盖消息封装和developer角色兼容转换。"""

    def measure(
        self, request: ProviderRequest, capacity: ModelCapacity
    ) -> TokenMeasurement:
        self._validate_request(request, capacity)
        options = _json_value(request.options)
        if not isinstance(options, dict):
            raise ContextCapacityError()
        for metadata in ("model", "logical_model", "timeout", "json_schema"):
            options.pop(metadata, None)
        maximum_body = 0
        maximum_bound = 0
        for developer_role in (True, False):
            payload = {
                **options,
                "model": capacity.model,
                "messages": [
                    _serialize_message(message, supports_developer_role=developer_role)
                    for message in request.messages
                ],
            }
            body = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            maximum_body = max(maximum_body, len(body))
            maximum_bound = max(
                maximum_bound, input_token_upper_bound("deepseek", body, payload)
            )
        return TokenMeasurement(
            total_upper_bound=maximum_bound,
            by_component=(
                ("request_body", maximum_body),
                ("serializer_overhead", maximum_bound - maximum_body),
            ),
            method="conservative-utf8/1",
            verified=True,
        )

    def measure_messages(
        self, messages: tuple[ProviderMessage, ...], capacity: ModelCapacity
    ) -> TokenMeasurement:
        """独立计消息片段上界；不把全请求固定4096余量重复计入槽位。"""
        fragment = ProviderRequest("context-fragment/1", messages, JsonObject(), 1000)
        self._validate_request(fragment, capacity)
        body_bound = max(
            len(
                json.dumps(
                    [
                        _serialize_message(message, supports_developer_role=developer)
                        for message in messages
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            )
            for developer in (True, False)
        )
        message_overhead = 256 * len(messages)
        return TokenMeasurement(
            total_upper_bound=body_bound + message_overhead,
            by_component=(
                ("messages_body", body_bound),
                ("message_overhead", message_overhead),
            ),
            method="conservative-utf8-fragment/1",
            verified=True,
        )

    @staticmethod
    def _validate_request(request: ProviderRequest, capacity: ModelCapacity) -> None:
        if (
            not isinstance(request, ProviderRequest)
            or not isinstance(capacity, ModelCapacity)
            or not capacity.verified
            or capacity.provider != "deepseek"
            or capacity.tokenizer_ref != "conservative-utf8/1"
            or capacity.serialization_ref != "openai-chat/1"
            or capacity.reasoning_rule
            not in {"OUTPUT_INCLUDES_REASONING", "NO_REASONING"}
            or capacity.context_window_tokens <= 0
            or capacity.max_output_tokens <= 0
            or capacity.max_input_tokens == 0
        ):
            raise ContextCapacityError()
        for message in request.messages:
            if not isinstance(message.content, str) and not (
                message.content is None
                and message.role == "assistant"
                and message.tool_calls
            ):
                raise ContextCapacityError()
