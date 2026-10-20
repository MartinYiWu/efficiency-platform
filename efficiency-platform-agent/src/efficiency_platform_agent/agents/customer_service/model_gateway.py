"""使用冻结 Release Prompt 调用结构化模型。"""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.core.run import (
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
)

from .release_bundle import CustomerServiceReleaseBundle, PromptMessage

T = TypeVar("T", bound=BaseModel)


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return JsonObject(
            tuple((str(key), _freeze(item)) for key, item in value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(f"不支持的 JSON 类型: {type(value).__name__}")


class ReleaseStructuredModelGateway:
    """Prompt 正文来自 Release；运行时代码只注入不可信 JSON 数据。"""

    def __init__(
        self, provider: ModelProvider, bundle: CustomerServiceReleaseBundle
    ) -> None:
        self.provider = provider
        self.bundle = bundle

    async def complete(
        self,
        stage_key: str,
        input_value: object,
        output_type: type[T],
    ) -> T:
        input_json = json.dumps(input_value, ensure_ascii=False, separators=(",", ":"))
        messages = tuple(
            self._render_message(message, input_json)
            for message in self._stage_messages(stage_key)
        )
        policy = self.bundle.model_policy
        schema = output_type.model_json_schema()
        result = await self.provider.complete(
            ProviderRequest(
                contract_version="provider-request/1",
                messages=messages,
                options=JsonObject(
                    (
                        ("logical_model", policy.model_name),
                        ("temperature", float(policy.temperature)),
                        ("top_p", float(policy.top_p)),
                        ("max_tokens", policy.max_output_tokens),
                        ("response_format", JsonObject((("type", "json_object"),))),
                        ("json_schema", _freeze(schema)),
                    )
                ),
                timeout_ms=policy.read_timeout_ms,
            )
        )
        if result.error is not None:
            raise StructuredModelError(result.error.code, result.error.safe_message)
        if result.message is None or not isinstance(result.message.content, str):
            raise StructuredModelError("MODEL_RESPONSE_INVALID", "模型未返回结构化文本")
        try:
            return output_type.model_validate_json(result.message.content)
        except ValueError as error:
            raise StructuredModelError(
                "MODEL_RESPONSE_INVALID", "模型返回不符合契约"
            ) from error

    def _stage_messages(self, stage_key: str) -> tuple[PromptMessage, ...]:
        shared = {"safety", "identity"}
        if stage_key in {
            "answer_company",
            "answer_mixed",
            "citation_review",
            "answer_repair",
            "output_guard",
        }:
            shared.add("citation")
        if stage_key in {"answer_general", "answer_mixed", "output_guard"}:
            shared.add("general_advice")
        selected = shared | {stage_key}
        bindings = sorted(
            (
                item
                for item in self.bundle.prompt_bindings
                if item.stage_key in selected
            ),
            key=lambda item: (
                item.stage_key not in {"safety", "identity"},
                item.stage_key,
                item.ordinal,
            ),
        )
        messages = tuple(message for item in bindings for message in item.messages)
        if not any(item.stage_key == stage_key for item in bindings):
            raise StructuredModelError(
                "PROMPT_STAGE_NOT_BOUND", f"Prompt 阶段未绑定: {stage_key}"
            )
        return messages

    @staticmethod
    def _render_message(message: PromptMessage, input_json: str) -> ProviderMessage:
        content = message.content_template
        if "{{input_json}}" in content:
            if message.role != "USER":
                raise StructuredModelError(
                    "PROMPT_TRUST_BOUNDARY_INVALID", "不可信输入只能进入 USER 消息"
                )
            content = content.replace("{{input_json}}", input_json)
        role = message.role.lower()
        return ProviderMessage(role=role, content=content)


class StructuredModelError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


__all__ = ["ReleaseStructuredModelGateway", "StructuredModelError"]
