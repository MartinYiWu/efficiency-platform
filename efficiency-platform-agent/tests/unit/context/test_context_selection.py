from dataclasses import FrozenInstanceError, replace

import pytest

from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.context.selection import select_context
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    SourceDependency,
)
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderToolCall,
)

SCOPE = ExecutionScope(
    ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s"),
    "task",
    "exec",
    "sub",
    "answer",
    "operations",
)
DEP = SourceDependency("message", "evidence", "1")
CAPACITY = ModelCapacity(
    "fake",
    "fake",
    "1",
    1000,
    None,
    100,
    "fake/1",
    "fake/1",
    "NO_REASONING",
    True,
    "offline-test",
)


class Counter:
    def measure(self, request, capacity):
        total = (
            10
            + sum(len(str(m.content).encode("utf-8")) for m in request.messages)
            + len(str(request.options.items))
        )
        return TokenMeasurement(total, (("complete", total),), "fake/1", True)


def piece(
    pid, text, *, required=False, kind="optional", priority=0, deps=(), covered=()
):
    return ContextPiece(
        pid,
        SCOPE,
        (ProviderMessage("user", text),),
        deps,
        required,
        priority,
        kind,
        covered,
    )


def policy(*, deps=(DEP,), ids=frozenset()):
    return ContextPolicy("node", "1", SCOPE, deps, ids)


def select(pieces, *, cap=200, pol=None, options=None):
    template = ProviderRequest(
        "1",
        tuple(m for p in pieces for m in p.messages),
        JsonObject() if options is None else options,
        1000,
    )
    return select_context(
        SCOPE,
        pol or policy(),
        pieces,
        WindowLimits(1000, None, 100, 0, cap),
        counter=Counter(),
        capacity=CAPACITY,
        request_template=template,
    )


def test_required_priority_full_request_and_immutable_view():
    required = piece("current", "必须保留否定和版本", kind="current_request")
    optional = piece("old", "x" * 180, priority=100)
    view = select((optional, required), cap=90)
    assert view.pieces == (required,)
    assert view.messages == required.messages
    assert view.measurement == Counter().measure(view.request, CAPACITY)
    assert view.decision.status == "ALLOW"
    assert ("old", "WINDOW_LIMIT") in view.exclusions
    with pytest.raises(FrozenInstanceError):
        view.messages = ()


def test_schema_overhead_can_make_required_impossible_without_truncation():
    required = piece("fact", "HR制度原文价格", kind="business_evidence", deps=(DEP,))
    view = select((required,), cap=100, options=JsonObject((("schema", "x" * 150),)))
    assert view.decision.status == "REJECT"
    assert view.decision.F > 100
    assert view.messages == required.messages
    assert view.selected_safety_dependencies == (DEP,)


def test_dedup_covered_history_and_omit_dependency():
    current = piece("current", "question", kind="current_request")
    history = piece("history", "old", kind="history", deps=(DEP,), covered=("m1",))
    duplicate = replace(history, piece_id="duplicate", priority=0)
    view = select((current, history, duplicate), pol=policy(ids=frozenset({"m1"})))
    assert view.pieces == (current, history)
    assert ("duplicate", "DUPLICATE_COVERAGE") in view.exclusions
    assert view.selected_safety_dependencies == (DEP,)
    omitted = select((current, history), cap=21, pol=policy(ids=frozenset({"m1"})))
    assert omitted.selected_safety_dependencies == ()


@pytest.mark.parametrize("change", ["scope", "dependency", "range", "task_only"])
def test_sources_never_expand_authorization(change):
    current = piece("current", "question", kind="current_request")
    old = piece("old", "private", kind="history", deps=(DEP,), covered=("m1",))
    pol = policy(ids=frozenset({"m1"}))
    if change == "scope":
        old = replace(old, scope=replace(SCOPE, execution_id="other"))
    elif change == "dependency":
        pol = policy(deps=(), ids=frozenset({"m1"}))
    elif change == "range":
        pol = policy(ids=frozenset())
    else:
        task_scope = replace(
            SCOPE,
            conversation=replace(
                SCOPE.conversation, session_kind="TASK_ONLY", session_id=None
            ),
        )
        pol = replace(pol, scope=task_scope)
        current, old = (
            replace(current, scope=task_scope),
            replace(old, scope=task_scope),
        )
        template = ProviderRequest(
            "1", current.messages + old.messages, JsonObject(), 1000
        )
        view = select_context(
            task_scope,
            pol,
            (current, old),
            WindowLimits(1000, None, 100, 0, 200),
            counter=Counter(),
            capacity=CAPACITY,
            request_template=template,
        )
        assert view.pieces == (current,)
        return
    view = select((current, old), pol=pol)
    assert view.pieces == (current,)
    assert view.selected_safety_dependencies == ()


def test_required_unauthorized_source_is_rejected_not_silently_removed():
    with pytest.raises(ValueError, match="CONTEXT_SOURCE_NOT_AUTHORIZED"):
        select(
            (piece("fact", "private", kind="business_evidence", deps=(DEP,)),),
            pol=policy(deps=()),
        )


def test_complete_tool_group_keeps_receipt_and_does_not_rewrite_status():
    call = ProviderMessage(
        "assistant", None, tool_calls=(ProviderToolCall("c", "lookup", JsonObject()),)
    )
    receipt = ProviderMessage("tool", "UNKNOWN", tool_call_id="c")
    tool = ContextPiece(
        "tool", SCOPE, (call, receipt), (DEP,), False, 0, "tool_group", ()
    )
    view = select((tool,), cap=20)
    assert view.messages == (call, receipt)
    assert view.decision.status == "REJECT"
    with pytest.raises(ValueError, match="CONTEXT_TOOL_GROUP_INVALID"):
        replace(tool, messages=(call,))
    with pytest.raises(ValueError, match="CONTEXT_TOOL_GROUP_INVALID"):
        replace(tool, messages=(receipt,))


def test_missing_template_messages_and_conflicting_coverage_fail_closed():
    current = piece("current", "question", kind="current_request")
    with pytest.raises(ValueError, match="CONTEXT_TEMPLATE_MISMATCH"):
        select_context(
            SCOPE,
            policy(),
            (current,),
            WindowLimits(1000, None, 100, 0, 200),
            counter=Counter(),
            capacity=CAPACITY,
            request_template=ProviderRequest(
                "1", (ProviderMessage("user", "other"),), JsonObject(), 100
            ),
        )
    a = piece("a", "must retain", kind="negation", covered=("same",))
    b = piece("b", "different fact", kind="business_evidence", covered=("same",))
    with pytest.raises(ValueError, match="CONTEXT_REQUIRED_COVERAGE_CONFLICT"):
        select((a, b), pol=policy(ids=frozenset({"same"})))


def test_history_requires_lineage_and_covered_range():
    current = piece("current", "question", kind="current_request")
    unsafe = piece("old", "untracked old answer", kind="history")
    view = select((current, unsafe))
    assert view.pieces == (current,)
    assert ("old", "SOURCE_DEPENDENCIES_REQUIRED") in view.exclusions


def test_summary_has_bounded_segment_and_memory_cannot_claim_extra_window():
    current = piece("current", "question", kind="current_request")
    summary = piece("summary", "x" * 510, kind="summary", deps=(DEP,), covered=("m1",))
    view = select((current, summary), cap=800, pol=policy(ids=frozenset({"m1"})))
    assert view.pieces == (current,)
    assert ("summary", "SLOT_LIMIT") in view.exclusions


def test_distinct_required_tool_groups_cannot_reuse_call_id():
    call = ProviderMessage(
        "assistant", None, tool_calls=(ProviderToolCall("c", "lookup", JsonObject()),)
    )
    a = ContextPiece(
        "a",
        SCOPE,
        (call, ProviderMessage("tool", "UNKNOWN", tool_call_id="c")),
        (DEP,),
        True,
        0,
        "tool_group",
        (),
    )
    b = replace(
        a,
        piece_id="b",
        messages=(call, ProviderMessage("tool", "SUCCEEDED", tool_call_id="c")),
    )
    with pytest.raises(ValueError, match="CONTEXT_TOOL_GROUP_INVALID"):
        select((a, b))


def test_d03_complete_counter_boundary_and_model_switch_offline():
    from efficiency_platform_agent.providers.llm.request_counter import (
        ConservativeRequestTokenCounter,
    )

    counter = ConservativeRequestTokenCounter()
    capacity = ModelCapacity(
        "deepseek",
        "synthetic-model",
        "fake/1",
        32768,
        None,
        4096,
        "conservative-utf8/1",
        "openai-chat/1",
        "OUTPUT_INCLUDES_REASONING",
        True,
        "fake-only-capacity-evidence",
    )
    required = piece(
        "current", '中文🙂https://example.test {"x":1}', kind="current_request"
    )
    options = JsonObject((("response_format", JsonObject((("type", "json_object"),))),))
    template = ProviderRequest("1", required.messages, options, 1000)
    total = counter.measure(template, capacity).total_upper_bound
    for delta, expected in [(0, "ALLOW"), (-1, "REJECT")]:
        limits = WindowLimits(total + delta + 100, None, 100, 0, total + delta)
        view = select_context(
            SCOPE,
            policy(),
            (required,),
            limits,
            counter=counter,
            capacity=replace(
                capacity, context_window_tokens=limits.context_window_tokens
            ),
            request_template=template,
        )
        assert view.decision.status == expected
        assert view.decision.T == view.decision.F == total
        assert view.measurement == counter.measure(view.request, capacity)
        assert view.request.options == options


def test_real_counter_keeps_short_memory_with_default_slots_and_omits_oversized():
    from efficiency_platform_agent.providers.llm.request_counter import (
        ConservativeRequestTokenCounter,
    )

    counter = ConservativeRequestTokenCounter()
    capacity = ModelCapacity(
        "deepseek",
        "synthetic-model",
        "fake/1",
        32768,
        None,
        4096,
        "conservative-utf8/1",
        "openai-chat/1",
        "OUTPUT_INCLUDES_REASONING",
        True,
        "fake-only-capacity-evidence",
    )
    current = piece(
        "current", "必需证据，否定条件保持原样", kind="business_evidence", deps=(DEP,)
    )
    memory = piece("memory", "偏好中文", kind="memory", deps=(DEP,))
    oversized = piece("oversized", "长" * 1000, kind="memory", deps=(DEP,))
    sources = (current, memory, oversized)
    template = ProviderRequest(
        "1", tuple(m for p in sources for m in p.messages), JsonObject(), 1000
    )
    view = select_context(
        SCOPE,
        policy(),
        sources,
        WindowLimits(32768, None, 4096, 0, 20000),
        counter=counter,
        capacity=capacity,
        request_template=template,
    )
    assert view.pieces == (current, memory)
    assert ("oversized", "SLOT_LIMIT") in view.exclusions
    assert view.measurement == counter.measure(view.request, capacity)
    assert (
        view.decision.F
        == counter.measure(
            replace(template, messages=current.messages), capacity
        ).total_upper_bound
    )
