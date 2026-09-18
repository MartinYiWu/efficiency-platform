"""Prompt Runtime 的契约与安全边界测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.prompts.contracts import PromptBundleSpec
from efficiency_platform_agent.prompts.registry import PromptRegistry
from efficiency_platform_agent.prompts.runtime import PromptRuntime

RESOURCE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "efficiency_platform_agent"
    / "prompts"
    / "resources"
)


def spec(
    prompt_id: str,
    template_path: str,
    required_variables: frozenset[str],
    *,
    max_rendered_chars: int = 2_000,
) -> PromptBundleSpec:
    """构造测试用 Prompt 元数据。"""
    return PromptBundleSpec(
        prompt_id=prompt_id,
        semantic_version="1.0.0",
        owner="platform",
        template_path=template_path,
        variable_schema_version="1.0.0",
        required_variables=required_variables,
        output_schema_version="1.0.0",
        allowed_model_tiers=frozenset({"standard"}),
        max_rendered_chars=max_rendered_chars,
    )


def registered_runtime() -> tuple[PromptRegistry, PromptRuntime]:
    """显式注册三份合成 Prompt。"""
    registry = PromptRegistry()
    registry.register(
        spec("direct.system", "direct_system_v1.j2", frozenset({"user_input"}))
    )
    registry.register(
        spec("workflow.draft", "workflow_draft_v1.j2", frozenset({"user_input"}))
    )
    registry.register(
        spec(
            "workflow.review",
            "workflow_review_v1.j2",
            frozenset({"draft", "lookup_result"}),
        )
    )
    return registry, PromptRuntime(registry, resource_root=RESOURCE_ROOT)


def test_three_prompts_render_versioned_provider_messages() -> None:
    """三份 Prompt 均能输出带版本的 system 消息。"""
    registry, runtime = registered_runtime()

    rendered = runtime.render("direct.system", {"user_input": "合成问题"})

    assert rendered.prompt_id == "direct.system"
    assert rendered.semantic_version == "1.0.0"
    assert rendered.output_schema_version == "1.0.0"
    assert rendered.rendered_chars > 0
    assert rendered.messages == (
        ProviderMessage("system", rendered.messages[0].content),
    )
    assert isinstance(rendered.messages[0].content, str)
    assert "合成问题" in rendered.messages[0].content
    assert "不可信用户输入" in rendered.messages[0].content
    assert registry.get("workflow.draft").template_path == "workflow_draft_v1.j2"


def test_registry_rejects_duplicate_and_unknown_prompt_ids() -> None:
    """Registry 只接受唯一显式 ID，未知 ID 必须失败关闭。"""
    registry = PromptRegistry()
    first = spec("direct.system", "direct_system_v1.j2", frozenset({"user_input"}))
    registry.register(first)

    with pytest.raises(ValueError):
        registry.register(first)
    with pytest.raises(KeyError):
        registry.get("missing")


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({}, "缺失"),
        ({"user_input": "x", "extra": "y"}, "额外"),
    ],
)
def test_render_rejects_missing_or_extra_variables(
    variables: dict[str, str], message: str
) -> None:
    """变量集合必须与版本化 Schema 完全一致。"""
    _, runtime = registered_runtime()

    with pytest.raises(ValueError, match=message):
        runtime.render("direct.system", variables)


def test_render_uses_strict_undefined_for_template_variables() -> None:
    """模板中未声明的变量不得静默渲染为空值。"""
    _, runtime = registered_runtime()
    runtime.registry.register(
        spec("broken", "direct_system_v1.j2", frozenset({"different"}))
    )

    with pytest.raises(ValueError, match="未定义"):
        runtime.render("broken", {"different": "x"})


def test_render_rejects_template_path_traversal() -> None:
    """模板路径解析后必须仍位于固定 resources 根目录内。"""
    registry = PromptRegistry()
    registry.register(spec("escape", "..\\secrets.j2", frozenset({"user_input"})))
    runtime = PromptRuntime(registry, resource_root=RESOURCE_ROOT)

    with pytest.raises(ValueError, match="路径"):
        runtime.render("escape", {"user_input": "x"})


def test_render_rejects_overlong_result() -> None:
    """渲染结果超过 Prompt 上限时必须拒绝。"""
    registry = PromptRegistry()
    registry.register(
        spec(
            "tiny",
            "direct_system_v1.j2",
            frozenset({"user_input"}),
            max_rendered_chars=20,
        )
    )
    runtime = PromptRuntime(registry, resource_root=RESOURCE_ROOT)

    with pytest.raises(ValueError, match="长度"):
        runtime.render("tiny", {"user_input": "这是一段超过限制的合成用户输入"})


def test_user_input_is_not_executed_as_a_second_template() -> None:
    """用户变量中的 Jinja 语法只作为不可信文本保留。"""
    _, runtime = registered_runtime()

    rendered = runtime.render("direct.system", {"user_input": "{{danger}}"})
    content = rendered.messages[0].content

    assert isinstance(content, str)
    assert "{{danger}}" in content
    assert "不可信用户输入" in content


def test_operation_factory_registers_v1_and_v2_prompts() -> None:
    """运营组合根显式注册两个契约版本的模板。"""
    from efficiency_platform_agent.harness import operation_agent_factory

    registry = operation_agent_factory.build_operation_prompt_registry()
    assert (
        registry.get("operation.deliverable.generation/1").output_schema_version
        == "deliverable/1"
    )
    spec = registry.get("operation.deliverable.generation/2")
    assert spec.output_schema_version == "deliverable/2"
    assert spec.required_variables == frozenset({"capability", "deliverable_kind"})
    rendered = PromptRuntime(registry).render(
        spec.prompt_id,
        {
            "capability": "operation.research.insight",
            "deliverable_kind": "ranked_digest",
        },
    )
    assert isinstance(rendered.messages[0].content, str)
    assert "Research Quality Gate" in rendered.messages[0].content
    assert "copy_text" in rendered.messages[0].content
