"""受治理 Prompt 模板的安全渲染运行时。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from efficiency_platform_agent.core.run import JsonValue, ProviderMessage

from .contracts import RenderedPrompt
from .registry import PromptRegistry


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
