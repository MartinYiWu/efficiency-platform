"""R05 Research V2 语义相关性 Prompt 的治理测试。"""

from __future__ import annotations

from efficiency_platform_agent.prompts.registry import (
    PromptRegistry,
    register_research_v2_prompts,
)
from efficiency_platform_agent.prompts.runtime import PromptRuntime


def test_relevance_prompt_is_explicitly_registered_and_versioned() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)

    spec = registry.get("research.v2.relevance")

    assert spec.semantic_version == "1.0.0"
    assert spec.output_schema_version == "semantic-relevance-decision/2"
    assert spec.required_variables == frozenset({"brief_schema", "decision_schema"})
    cluster = registry.get("research.v2.cluster")
    assert cluster.semantic_version == "1.0.0"
    assert cluster.output_schema_version == "cluster-proposal/2"


def test_relevance_prompt_keeps_documents_out_of_system_template() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)
    rendered = PromptRuntime(registry).render(
        "research.v2.relevance",
        {"brief_schema": "BRIEF_SCHEMA", "decision_schema": "DECISION_SCHEMA"},
    )

    content = rendered.messages[0].content
    assert isinstance(content, str)
    for expected in (
        "USER_UNTRUSTED",
        "不使用关键词缺失直接判 irrelevant",
        "无法从规范正文得到可靠结论时输出 uncertain",
        "source_excerpt 必须逐字来自",
        "requirement_ids 只能选择",
        "唯一 ContextBuilder",
        "仅输出符合 decision_schema 的 JSON",
    ):
        assert expected in content
    assert "BRIEF_SCHEMA" in content
    assert "DECISION_SCHEMA" in content


def test_cluster_prompt_forbids_cross_bucket_and_forced_merge() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)

    content = (
        PromptRuntime(registry)
        .render(
            "research.v2.cluster",
            {"brief_schema": "BRIEF_SCHEMA", "proposal_schema": "PROPOSAL_SCHEMA"},
        )
        .messages[0]
        .content
    )

    assert isinstance(content, str)
    for expected in (
        "唯一 ContextBuilder",
        "USER_UNTRUSTED",
        "不得创造、改写或跨 bucket",
        "主题相似",
        "产品 v1/v2",
        "无法确认版本或事件等价时输出 uncertain",
        "转载数量不能变成多个独立佐证",
        "只输出符合 proposal_schema 的 JSON",
    ):
        assert expected in content


def test_claim_prompt_treats_source_text_as_data_and_forbids_url_generation() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)

    content = (
        PromptRuntime(registry)
        .render(
            "research.v2.claims",
            {
                "claim_schema": "CLAIM_SCHEMA",
                "evidence_schema": "EVIDENCE_SCHEMA",
                "event_schema": "EVENT_SCHEMA",
            },
        )
        .messages[0]
        .content
    )

    assert isinstance(content, str)
    for expected in (
        "唯一 ContextBuilder",
        "USER_UNTRUSTED",
        "不得生成、猜测或改写 URL",
        "不得把 9 改成 90",
        "announcement、reported_fact、measured_result、opinion 或 inference",
        "assertion_mode=attributed",
        "不能多数投票",
        "不得自行选多数值",
    ):
        assert expected in content


def test_replan_prompt_limits_model_to_gap_action_proposals() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)

    spec = registry.get("research.v2.replan")
    assert spec.semantic_version == "1.0.0"
    assert spec.output_schema_version == "collection-plan/2"
    assert spec.required_variables == frozenset(
        {"action_policy", "brief_schema", "plan_schema", "quality_schema"}
    )

    content = (
        PromptRuntime(registry)
        .render(
            "research.v2.replan",
            {
                "action_policy": "ACTION_POLICY",
                "brief_schema": "BRIEF_SCHEMA",
                "plan_schema": "PLAN_SCHEMA",
                "quality_schema": "QUALITY_SCHEMA",
            },
        )
        .messages[0]
        .content
    )

    assert isinstance(content, str)
    for expected in (
        "唯一 ContextBuilder",
        "USER_UNTRUSTED",
        "不得扩大原时间窗",
        "verified_free=true",
        "事实正确性、发布时间、原始来源、冲突或正文缺失",
        "不得返回 RESEARCH_COMPLETE 或 QUALITY_MET",
        "只由程序 QualityEvaluator 决定",
        "只输出符合 plan_schema 的 JSON",
        "ACTION_POLICY",
        "BRIEF_SCHEMA",
        "QUALITY_SCHEMA",
        "PLAN_SCHEMA",
    ):
        assert expected in content


def test_compose_and_verify_prompts_cannot_generate_urls_or_escalate_status() -> None:
    registry = PromptRegistry()
    register_research_v2_prompts(registry)
    runtime = PromptRuntime(registry)

    compose = (
        runtime.render(
            "research.v2.compose",
            {
                "brief_schema": "BRIEF_SCHEMA",
                "draft_schema": "DRAFT_SCHEMA",
                "evidence_schema": "EVIDENCE_SCHEMA",
            },
        )
        .messages[0]
        .content
    )
    verify = (
        runtime.render(
            "research.v2.verify",
            {
                "decision_schema": "DECISION_SCHEMA",
                "draft_schema": "DRAFT_SCHEMA",
                "evidence_schema": "EVIDENCE_SCHEMA",
            },
        )
        .messages[0]
        .content
    )

    assert isinstance(compose, str)
    assert isinstance(verify, str)
    for expected in (
        "唯一 ContextBuilder",
        "USER_UNTRUSTED",
        "不得生成、猜测、改写或复制 URL",
        "不得把 PARTIAL、NO_MATCHES 或 FAILED 改成 COMPLETE",
        "[evidence:已有 evidence_id]",
        "不得使用“全网”",
    ):
        assert expected in compose
    for expected in (
        "唯一 ContextBuilder",
        "USER_UNTRUSTED",
        "PARTIAL 升 COMPLETE",
        "引用断链",
        "不得生成、猜测或改写 URL",
        "最终 ACCEPT/REVISE/RECOLLECT/REJECT 由程序重新计算",
    ):
        assert expected in verify
