"""使用冻结 Release Prompt 调用结构化模型。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from efficiency_platform_agent.core.ports import ModelProvider, StreamingModelProvider
from efficiency_platform_agent.core.run import (
    JsonObject,
    JsonValue,
    ProviderMessage,
    ProviderRequest,
)

from .chunking import count_tokens
from .release_bundle import CustomerServiceReleaseBundle, ModelPolicy, PromptMessage

T = TypeVar("T", bound=BaseModel)


def _log_validation_error(
    stage_key: str, error: ValueError, output_type: type[BaseModel]
) -> None:
    schema = output_type.model_json_schema()
    field_names = set(schema.get("properties", {}))
    for definition in schema.get("$defs", {}).values():
        field_names.update(definition.get("properties", {}))
    fields = (
        [
            {
                "loc": tuple(
                    part
                    if isinstance(part, int) or part in field_names
                    else "[unknown_field]"
                    for part in item["loc"]
                ),
                "type": item["type"],
            }
            for item in error.errors(
                include_url=False, include_context=False, include_input=False
            )[:10]
        ]
        if isinstance(error, ValidationError)
        else []
    )
    logging.getLogger("efficiency_platform_agent.execution").warning(
        "event=customer_service_model_contract_invalid stage=%s fields=%s",
        stage_key,
        fields,
    )


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


def _answer_thinking_option(stage_key: str) -> tuple[tuple[str, JsonValue], ...]:
    # 冲突和充分性判断保留模型默认思考；已冻结证据的表述阶段优先缩短首段等待。
    if stage_key in {"answer_company", "answer_mixed", "answer_general"}:
        return (("thinking", JsonObject((("type", "disabled"),))),)
    return ()


def prompt_input_tokens(
    bundle: CustomerServiceReleaseBundle,
    stage_key: str,
    input_value: object,
    output_type: type[BaseModel],
) -> int:
    return sum(
        count_tokens(content) + 8
        for _, content in _request_text_messages(
            bundle, stage_key, input_value, output_type
        )
    )


def _request_text_messages(
    bundle: CustomerServiceReleaseBundle,
    stage_key: str,
    input_value: object,
    output_type: type[BaseModel],
) -> tuple[tuple[str, str], ...]:
    input_json = json.dumps(input_value, ensure_ascii=False, separators=(",", ":"))
    messages = tuple(
        _render_message(message, input_json)
        for message in stage_prompt_messages(bundle, stage_key)
    )
    return messages + (
        (
            "developer",
            "[OUTPUT CONTRACT]\n只返回一个符合下列 JSON Schema 的 JSON 对象，不要输出 Markdown、解释或代码围栏。\nJSON Schema:\n"
            + json.dumps(
                output_type.model_json_schema(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def stage_prompt_messages(
    bundle: CustomerServiceReleaseBundle, stage_key: str
) -> tuple[PromptMessage, ...]:
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
        (item for item in bundle.prompt_bindings if item.stage_key in selected),
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


def _render_message(message: PromptMessage, input_json: str) -> tuple[str, str]:
    content = message.content_template
    if "{{input_json}}" in content:
        if message.role != "USER":
            raise StructuredModelError(
                "PROMPT_TRUST_BOUNDARY_INVALID", "不可信输入只能进入 USER 消息"
            )
        content = content.replace("{{input_json}}", input_json)
    role = message.role.lower()
    return role, content


class ReleaseStructuredModelGateway:
    """Prompt 正文来自 Release；运行时代码只注入不可信 JSON 数据。"""

    def __init__(
        self, provider: ModelProvider, bundle: CustomerServiceReleaseBundle
    ) -> None:
        self.provider = provider
        self.bundle = bundle
        self.model_policy = bundle.model_policy

    def with_model_policy(self, policy: ModelPolicy) -> ReleaseStructuredModelGateway:
        if policy not in (
            self.bundle.model_policy,
            self.bundle.large_context_model_policy,
        ):
            raise StructuredModelError("MODEL_POLICY_NOT_BOUND", "模型策略未绑定")
        gateway = ReleaseStructuredModelGateway(self.provider, self.bundle)
        gateway.model_policy = policy
        return gateway

    def input_tokens(
        self, stage_key: str, input_value: object, output_type: type[BaseModel]
    ) -> int:
        return prompt_input_tokens(self.bundle, stage_key, input_value, output_type)

    def _request_messages(
        self, stage_key: str, input_value: object, output_type: type[BaseModel]
    ) -> tuple[ProviderMessage, ...]:
        return tuple(
            ProviderMessage(role=role, content=content)
            for role, content in _request_text_messages(
                self.bundle, stage_key, input_value, output_type
            )
        )

    async def complete(
        self,
        stage_key: str,
        input_value: object,
        output_type: type[T],
    ) -> T:
        started = perf_counter()
        messages = self._request_messages(stage_key, input_value, output_type)
        policy = self.model_policy
        schema = output_type.model_json_schema()
        if (
            self.bundle.contract_version.endswith("/2")
            and self.input_tokens(stage_key, input_value, output_type)
            + policy.max_output_tokens
            + max(256, policy.max_input_tokens // 10)
            > policy.max_input_tokens
        ):
            raise StructuredModelError(
                "MODEL_INPUT_BUDGET_EXCEEDED", "完整输入超过模型预算"
            )
        options = JsonObject(
            (
                ("logical_model", policy.model_name),
                ("temperature", float(policy.temperature)),
                ("top_p", float(policy.top_p)),
                ("max_tokens", policy.max_output_tokens),
                ("response_format", JsonObject((("type", "json_object"),))),
                ("json_schema", _freeze(schema)),
            )
            + _answer_thinking_option(stage_key)
        )
        for attempt in range(policy.max_retries + 1):
            attempt_messages = messages
            if attempt:
                attempt_messages += (
                    ProviderMessage(
                        role="developer",
                        content=(
                            "前一次输出未通过 JSON Schema 校验。重新生成完整 JSON 对象，"
                            "严格遵守字段名、必填项、类型、枚举和额外字段限制。"
                        ),
                    ),
                )
            result = await self.provider.complete(
                ProviderRequest(
                    contract_version="provider-request/1",
                    messages=attempt_messages,
                    options=options,
                    timeout_ms=policy.read_timeout_ms,
                )
            )
            if result.error is not None:
                if (
                    result.error.code == "PROVIDER_SCHEMA_INVALID"
                    and attempt < policy.max_retries
                ):
                    continue
                raise StructuredModelError(result.error.code, result.error.safe_message)
            if result.message is None or not isinstance(result.message.content, str):
                raise StructuredModelError(
                    "MODEL_RESPONSE_INVALID", "模型未返回结构化文本"
                )
            try:
                value = output_type.model_validate_json(result.message.content)
                logging.getLogger("efficiency_platform_agent.execution").info(
                    "event=customer_service_model_timing stage=%s elapsed_ms=%.0f input_tokens=%s",
                    stage_key,
                    (perf_counter() - started) * 1000,
                    self.input_tokens(stage_key, input_value, output_type),
                )
                return value
            except ValueError as error:
                _log_validation_error(stage_key, error, output_type)
                if attempt < policy.max_retries:
                    continue
                raise StructuredModelError(
                    "MODEL_RESPONSE_INVALID", "模型返回不符合契约"
                ) from error
        raise AssertionError("结构化模型重试循环未返回")

    async def stream_complete(
        self,
        stage_key: str,
        input_value: object,
        output_type: type[T],
        on_content: Callable[[str], None],
    ) -> T:
        if not isinstance(self.provider, StreamingModelProvider):
            return await self.complete(stage_key, input_value, output_type)
        started = perf_counter()
        if (
            self.bundle.contract_version.endswith("/2")
            and self.input_tokens(stage_key, input_value, output_type)
            + self.model_policy.max_output_tokens
            + max(256, self.model_policy.max_input_tokens // 10)
            > self.model_policy.max_input_tokens
        ):
            raise StructuredModelError(
                "MODEL_INPUT_BUDGET_EXCEEDED", "完整输入超过模型预算"
            )
        request = ProviderRequest(
            contract_version="provider-request/1",
            messages=self._request_messages(stage_key, input_value, output_type),
            options=JsonObject(
                (
                    ("logical_model", self.model_policy.model_name),
                    ("temperature", float(self.model_policy.temperature)),
                    ("top_p", float(self.model_policy.top_p)),
                    ("max_tokens", self.model_policy.max_output_tokens),
                    ("response_format", JsonObject((("type", "json_object"),))),
                    ("json_schema", _freeze(output_type.model_json_schema())),
                )
                + _answer_thinking_option(stage_key)
            ),
            timeout_ms=self.model_policy.read_timeout_ms,
        )
        parts: list[str] = []
        finished = False
        async for chunk in self.provider.stream(request):
            if chunk.error is not None:
                raise StructuredModelError(chunk.error.code, chunk.error.safe_message)
            if chunk.delta:
                parts.append(chunk.delta)
                on_content("".join(parts))
            finished = finished or chunk.finish_reason is not None
        if not finished:
            raise StructuredModelError(
                "PROVIDER_RESPONSE_TRUNCATED", "模型流未正常结束"
            )
        try:
            value = output_type.model_validate_json("".join(parts))
        except ValueError as error:
            _log_validation_error(stage_key, error, output_type)
            raise StructuredModelError(
                "MODEL_RESPONSE_INVALID", "模型返回不符合契约"
            ) from error
        logging.getLogger("efficiency_platform_agent.execution").info(
            "event=customer_service_model_timing stage=%s elapsed_ms=%.0f input_tokens=%s",
            stage_key,
            (perf_counter() - started) * 1000,
            self.input_tokens(stage_key, input_value, output_type),
        )
        return value


class StructuredModelError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


__all__ = [
    "ReleaseStructuredModelGateway",
    "StructuredModelError",
    "prompt_input_tokens",
    "stage_prompt_messages",
]
