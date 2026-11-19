"""CSR确切JSON history投影与负例；不调用模型/数据库。"""

import json
from dataclasses import replace
from hashlib import sha256

from efficiency_platform_agent.context.controller import ExactHistoryContextPolicy
from efficiency_platform_agent.context.policy import (
    ContextPiece,
    render_context_messages,
)
from efficiency_platform_agent.context.selection import select_context
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import model_stage
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    SourceDependency,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.harness.memory_summary_context import (
    OriginalMessageProjection,
    project_csr_original_messages,
)
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)


def fixture():
    scope = ExecutionScope(
        ConversationScope(
            "tenant",
            "user",
            "customer-service",
            "customer-service",
            "CONVERSATION",
            "session",
        ),
        "task",
        "execution",
        "customer-service:answer_general",
        "assistant_response",
        "customer-service",
    )
    dep = SourceDependency(
        "MESSAGE", "history-user", sha256("历史完整原文".encode()).hexdigest(), 0, 1, 0
    )
    history = [
        {"role": "user", "content": "历史完整原文"},
        {"role": "assistant", "content": "以前的普通建议"},
    ]
    other = SourceDependency(
        "MESSAGE",
        "history-assistant",
        sha256(history[1]["content"].encode()).hexdigest(),
        0,
        1,
        0,
    )
    inputs = {
        "question": "当前问题😀",
        "history": history,
        "evidence": [],
        "sufficiency": None,
        "intent": {"intent_type": "GENERAL_QUERY", "requires_company_knowledge": False},
        "unknown_required": {"keep": '原值\\"'},
    }
    encoded = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    request = ProviderRequest(
        "provider-request/1",
        (
            ProviderMessage("system", "原system不变"),
            ProviderMessage("user", "可信前缀\n" + encoded + "\n可信后缀"),
            ProviderMessage("developer", "原Schema不变"),
        ),
        JsonObject(),
        1000,
    )
    projections = tuple(
        OriginalMessageProjection(
            identifier,
            item["role"],
            sha256(item["content"].encode()).hexdigest(),
            (dependency,),
            True,
        )
        for identifier, item, dependency in zip(
            ("history-user", "history-assistant"), history, (dep, other), strict=True
        )
    )
    semantic = json.dumps(
        {"stage_key": "answer_general", "input_value": inputs}, ensure_ascii=False
    ).encode()
    return scope, request, projections, semantic, inputs, (dep, other)


def test_exact_json_history_reconstruction_keeps_every_nonhistory_field_and_complete_counter():
    scope, request, projections, semantic, inputs, deps = fixture()
    with model_stage("stage", semantic, node_id="customer-service:answer_general"):
        projected = project_csr_original_messages(
            request, scope, projections, required_dependencies=deps
        )
    assert projected is not None
    pieces, renderer = projected
    policy = ExactHistoryContextPolicy(
        "customer-service:answer_general",
        "window/1",
        scope,
        authorized_dependencies=deps,
        allowed_message_ids=frozenset(p.message_id for p in projections),
        json_history=renderer,
    )
    assert render_context_messages(policy, pieces) == request.messages
    capacity = ModelCapacity(
        "deepseek",
        "deepseek-chat",
        "1",
        64000,
        None,
        500,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "offline",
    )
    counter = ConservativeRequestTokenCounter()
    view = select_context(
        scope,
        policy,
        pieces,
        WindowLimits(64000, None, 500, 0, 63000),
        counter=counter,
        capacity=capacity,
        request_template=request,
    )
    assert view.request == request
    summary = ContextPiece(
        "summary:segment",
        scope,
        (ProviderMessage("user", "已保存普通对话摘要"),),
        deps,
        kind="summary",
        covered_message_ids=tuple(p.message_id for p in projections),
    )
    changed = tuple(p for p in pieces if p.kind != "history")
    changed = (summary, *changed)
    messages = render_context_messages(policy, changed)
    assert messages[0] == request.messages[0] and messages[-1] == request.messages[-1]
    content = messages[1].content
    value = json.loads(content.removeprefix("可信前缀\n").removesuffix("\n可信后缀"))
    assert {k: v for k, v in value.items() if k != "history"} == {
        k: v for k, v in inputs.items() if k != "history"
    }
    assert value["history"] == [{"role": "user", "content": "已保存普通对话摘要"}]
    # 以真实D20候选校验/完整请求计窗验证JSON重建的净收益，而非只测字符串替换。
    from efficiency_platform_agent.memory.summary_validation import validate_summary
    from tests.unit.context.test_compaction_benefit import setup

    api, original, validated, counter = setup(history_length=1000)
    csr_scope = validated.segment.scope.model_copy(
        update={"domain": "customer-service", "top_level_agent_id": "customer-service"}
    )
    source = validated.frozen_sources.sources[0].model_copy(update={"scope": csr_scope})
    frozen = replace(validated.frozen_sources, sources=(source,))
    state = replace(validated.task_state, scope=csr_scope, current_sources=(source,))
    candidate = validate_summary(
        validated.segment.model_copy(update={"scope": csr_scope}), frozen, state
    )
    execution = replace(scope, conversation=csr_scope.to_core())
    body = "原始历史" * 1000
    payload = {
        "question": "当前问题",
        "history": [{"role": "user", "content": body}],
        "evidence": [],
        "sufficiency": None,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    actual = ProviderRequest(
        "provider-request/1",
        (
            ProviderMessage("system", "不可改system"),
            ProviderMessage("user", encoded),
            ProviderMessage("developer", "不可改Schema"),
        ),
        JsonObject(),
        1000,
    )
    dependency = source.source_ref.to_core()
    projection = (
        OriginalMessageProjection(
            "m1", "user", sha256(body.encode()).hexdigest(), (dependency,), True
        ),
    )
    semantic = json.dumps(
        {"stage_key": "answer_general", "input_value": payload}, ensure_ascii=False
    ).encode()
    with model_stage("stage", semantic, node_id="customer-service:answer_general"):
        result = project_csr_original_messages(
            actual, execution, projection, required_dependencies=()
        )
    assert result is not None
    pieces, renderer = result
    policy = ExactHistoryContextPolicy(
        "customer-service:answer_general",
        original.window_policy_version,
        execution,
        authorized_dependencies=(dependency,),
        allowed_message_ids=frozenset({"m1"}),
        history_token_limit=150000,
        json_history=renderer,
    )
    view = select_context(
        execution,
        policy,
        pieces,
        original.limits,
        counter=counter,
        capacity=original.capacity,
        request_template=actual,
    )
    decision = api.propose_compaction(
        replace(original, view=view, window_policy=policy), candidate, counter
    )
    assert decision.status == "BENEFICIAL" and decision.T_after < decision.T_before
    output = next(
        message for message in decision.request.messages if message.role == "user"
    )
    rendered = json.loads(output.content)
    assert (
        rendered["question"] == payload["question"]
        and rendered["evidence"] == []
        and rendered["sufficiency"] is None
    )
    assert any(message == actual.messages[0] for message in decision.request.messages)
    assert any(message == actual.messages[-1] for message in decision.request.messages)


def test_json_wrong_hash_partial_group_or_factknowledge_stage_never_projects():
    scope, request, projections, semantic, _, deps = fixture()
    for invalid in (
        (replace(projections[0], content_sha256="f" * 64), projections[1]),
        (replace(projections[0], group_completed=False), projections[1]),
    ):
        with model_stage("stage", semantic, node_id="customer-service:answer_general"):
            assert (
                project_csr_original_messages(
                    request, scope, invalid, required_dependencies=deps
                )
                is None
            )
    for node in (
        "customer-service:intent",
        "customer-service:answer_company",
        "customer-service:answer_mixed",
    ):
        with model_stage("stage", semantic, node_id=node):
            assert (
                project_csr_original_messages(
                    request, scope, projections, required_dependencies=deps
                )
                is None
            )
    value = json.loads(semantic)
    value["input_value"]["evidence"] = [{"fact": "原知识必保"}]
    with model_stage(
        "stage",
        json.dumps(value, ensure_ascii=False).encode(),
        node_id="customer-service:answer_general",
    ):
        assert (
            project_csr_original_messages(
                request, scope, projections, required_dependencies=deps
            )
            is None
        )
