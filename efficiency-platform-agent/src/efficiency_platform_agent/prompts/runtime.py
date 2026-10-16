"""受治理 Prompt 模板的安全渲染运行时。"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from efficiency_platform_agent.core.run import JsonValue, ProviderMessage

from .contracts import (
    AssembledPrompt,
    PromptMessage,
    PromptValue,
    RenderedPrompt,
    RunPromptSnapshot,
)
from .registry import PromptRegistry
from .repository import PromptConfigurationError, PromptRepository


class PromptRuntime:
    """从固定 resources 根目录读取并渲染显式登记的 Prompt。"""

    def __init__(
        self, registry: PromptRegistry, *, resource_root: Path | None = None
    ) -> None:
        if not isinstance(registry, PromptRegistry):
            raise TypeError("registry 必须为 PromptRegistry")
        root = resource_root or Path(__file__).with_name("resources")
        self.registry = registry
        self._resource_root = root.resolve()
        self._environment = ImmutableSandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )

    def render(
        self, prompt_id: str, variables: Mapping[str, JsonValue]
    ) -> RenderedPrompt:
        """严格校验变量、路径和输出长度后返回 ProviderMessage 契约。"""
        spec = self.registry.get(prompt_id)
        if not isinstance(variables, Mapping):
            raise TypeError("variables 必须为 Mapping")
        actual = set(variables)
        expected = set(spec.required_variables)
        missing = expected - actual
        extra = actual - expected
        if missing:
            raise ValueError(f"缺失 Prompt 变量: {sorted(missing)}")
        if extra:
            raise ValueError(f"额外 Prompt 变量: {sorted(extra)}")

        template_file = (self._resource_root / spec.template_path).resolve()
        try:
            template_file.relative_to(self._resource_root)
        except ValueError as exc:
            raise ValueError("模板路径越出固定 resources 根目录") from exc
        if not template_file.is_file():
            raise ValueError("模板路径不存在或不是文件")

        try:
            source = template_file.read_text(encoding="utf-8")
            content = self._environment.from_string(source).render(dict(variables))
        except TemplateError as exc:
            raise ValueError(f"Prompt 模板未定义变量或渲染失败: {exc}") from exc
        rendered_chars = len(content)
        if rendered_chars > spec.max_rendered_chars:
            raise ValueError("Prompt 渲染结果长度超过上限")
        return RenderedPrompt(
            prompt_id=spec.prompt_id,
            semantic_version=spec.semantic_version,
            output_schema_version=spec.output_schema_version,
            messages=(ProviderMessage("system", content),),
            rendered_chars=rendered_chars,
        )


class PromptAssembler:
    """从数据库资产解析并冻结一次 Run/Stage 使用的多角色 Prompt。"""

    def __init__(self, repository: PromptRepository, *, environment: str) -> None:
        if not isinstance(environment, str) or not environment.strip():
            raise ValueError("environment 必须为非空字符串")
        self._repository = repository
        self._environment_name = environment.strip()
        self._template_environment = ImmutableSandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )

    async def assemble(
        self,
        *,
        run_id: str,
        stage: str,
        prompt_key: str,
        variables: Mapping[str, PromptValue],
    ) -> AssembledPrompt:
        if not isinstance(variables, Mapping):
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_INVALID", "variables 必须为 Mapping"
            )
        bundle = await self._repository.load_snapshot(run_id, stage)
        snapshot_exists = bundle is not None
        if bundle is None:
            bundle = await self._repository.resolve(
                prompt_key, self._environment_name
            )

        from .mysql_repository import validate_prompt_bundle

        validate_prompt_bundle(bundle)
        if bundle.definition.prompt_key != prompt_key:
            raise PromptConfigurationError(
                "PROMPT_SNAPSHOT_MISMATCH",
                f"stage={stage} 已冻结为 {bundle.definition.prompt_key}",
            )

        definitions = self._variable_definitions(bundle.variables)
        actual_names = set(variables)
        expected_names = set(definitions)
        missing = {
            name
            for name, definition in definitions.items()
            if definition.required and name not in actual_names
        }
        if missing:
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_MISSING", ",".join(sorted(missing))
            )
        unknown = actual_names - expected_names
        if unknown:
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_UNKNOWN", ",".join(sorted(unknown))
            )

        render_values: dict[str, object] = {}
        variable_snapshot: dict[str, object] = {}
        for name, definition in definitions.items():
            prompt_value = variables.get(name)
            if prompt_value is None:
                render_values[name] = None
                continue
            if not isinstance(prompt_value, PromptValue):
                raise PromptConfigurationError(
                    "PROMPT_VARIABLE_INVALID", f"{name} 必须为 PromptValue"
                )
            if prompt_value.source != definition.value_source:
                raise PromptConfigurationError(
                    "PROMPT_VARIABLE_SOURCE_INVALID",
                    f"{name} 期望 {definition.value_source}，实际 {prompt_value.source}",
                )
            normalized = self._normalize_value(
                name, definition.value_type, prompt_value.value
            )
            serialized = self._serialize_value(normalized)
            if len(serialized) > definition.max_length:
                raise PromptConfigurationError(
                    "PROMPT_VARIABLE_TOO_LONG", name
                )
            render_values[name] = serialized if definition.value_type == "json" else normalized
            variable_snapshot[name] = {
                "source": prompt_value.source,
                "sensitive": definition.sensitive,
                "value_hash": self._sha256(serialized),
            }

        messages: list[PromptMessage] = []
        try:
            for template in sorted(bundle.messages, key=lambda item: item.ordinal):
                content = self._template_environment.from_string(
                    template.content_template
                ).render(render_values)
                messages.append(PromptMessage(template.role, content))
        except TemplateError as exc:
            raise PromptConfigurationError(
                "PROMPT_RENDER_FAILED", str(exc)
            ) from exc

        rendered_payload = [
            {"role": message.role, "content": message.content}
            for message in messages
        ]
        rendered_checksum = self._sha256(
            json.dumps(rendered_payload, ensure_ascii=False, sort_keys=True)
        )
        template_checksum = self._sha256(
            "|".join(message.checksum for message in bundle.messages)
        )
        values_checksum = self._sha256(
            json.dumps(variable_snapshot, ensure_ascii=False, sort_keys=True)
        )

        if not snapshot_exists:
            await self._repository.save_snapshot(
                RunPromptSnapshot(
                    run_id=run_id,
                    stage=stage,
                    prompt_definition_id=bundle.definition.id,
                    prompt_version_id=bundle.version.id,
                    model_policy_id=bundle.model_policy.id,
                    output_contract_id=bundle.output_contract.id,
                    message_checksum=template_checksum,
                    rendered_messages_checksum=rendered_checksum,
                    variable_values_checksum=values_checksum,
                    referenced_snapshot={
                        "prompt_key": bundle.definition.prompt_key,
                        "semantic_version": bundle.version.semantic_version,
                        "variables": variable_snapshot,
                    },
                    created_at_epoch_ms=int(time.time() * 1000),
                )
            )

        return AssembledPrompt(
            prompt_key=bundle.definition.prompt_key,
            semantic_version=bundle.version.semantic_version,
            messages=tuple(messages),
            model_policy=bundle.model_policy,
            output_contract=bundle.output_contract,
            message_checksum=rendered_checksum,
            rendered_chars=sum(len(message.content) for message in messages),
        )

    @staticmethod
    def _variable_definitions(variables):
        definitions = {}
        for definition in variables:
            existing = definitions.get(definition.variable_name)
            if existing is not None and existing != definition:
                raise PromptConfigurationError(
                    "PROMPT_VARIABLE_DUPLICATE", definition.variable_name
                )
            definitions[definition.variable_name] = definition
        return definitions

    @staticmethod
    def _normalize_value(name: str, value_type: str, value: object) -> object:
        valid = False
        if value_type == "string":
            valid = isinstance(value, str)
        elif value_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif value_type == "boolean":
            valid = isinstance(value, bool)
        elif value_type == "json":
            try:
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                valid = True
            except (TypeError, ValueError):
                valid = False
        elif (
            value_type == "string_list"
            and isinstance(value, (list, tuple))
            and all(isinstance(item, str) for item in value)
        ):
            return list(value)
        if not valid:
            raise PromptConfigurationError(
                "PROMPT_VARIABLE_TYPE_INVALID", f"{name}:{value_type}"
            )
        return value

    @staticmethod
    def _serialize_value(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
