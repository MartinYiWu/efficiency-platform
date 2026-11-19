from dataclasses import replace
from importlib import import_module

import pytest

from efficiency_platform_agent.contracts.memory import MemoryProposalModel
from efficiency_platform_agent.core.memory import MemoryPolicy
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from tests.unit.context.test_compaction_benefit import setup
from tests.unit.memory.test_summary_contracts import scope, source


def fixture():
    api = import_module("efficiency_platform_agent.memory.proposals")
    conflicts = import_module("efficiency_platform_agent.memory.conflicts")
    policy = MemoryPolicy(
        "p",
        "v1",
        "operations",
        frozenset({"operations"}),
        writable_kinds=frozenset({"PREFERENCE"}),
        allowed_scopes=frozenset({"USER_PRIVATE"}),
        field_allowlist=frozenset({"response.language"}),
        auto_extract=True,
    )
    state = api.ProposalTaskState(
        scope(), "task", policy, (source(),), (), frozenset(), frozenset()
    )
    capacity = setup()[1].capacity
    proposal = MemoryProposalModel(
        kind="PREFERENCE", field_key="response.language", value="zh-CN"
    )
    return api, conflicts, state, capacity, proposal


def test_scope_and_source_revocation_cannot_relearn_under_new_item_or_policy():
    api, _, state, capacity, proposal = fixture()
    evaluate = lambda candidate, current: api.evaluate_proposals(
        candidate, current, ConservativeRequestTokenCounter(), capacity, now=1
    )
    with pytest.raises(ValueError, match="PROPOSAL_SOURCE_SUPPRESSED"):
        evaluate(
            (proposal,),
            replace(state, suppressed_sources=frozenset({("MESSAGE", "m1")})),
        )
    with pytest.raises(ValueError, match="PROPOSAL_FIELD_SUPPRESSED"):
        evaluate(
            (proposal,),
            replace(state, suppressed_fields=frozenset({"response.language"})),
        )
    with pytest.raises(ValueError, match="SUMMARY_SCOPE_MISMATCH"):
        evaluate(
            (proposal,),
            replace(state, scope=scope().model_copy(update={"user_id": "other"})),
        )
    with pytest.raises(ValueError, match="SUMMARY_PURPOSE_DENIED"):
        evaluate(
            (proposal,),
            replace(state, sources=(source(allowed_purposes=frozenset({"SUMMARY"})),)),
        )


def test_conflicting_sources_require_decision_and_never_choose_latest_value():
    api, conflicts, state, capacity, proposal = fixture()
    current = (
        conflicts.CurrentFieldValue(
            "item-a", "v1", "PREFERENCE", "response.language", "en-US", 1
        ),
        conflicts.CurrentFieldValue(
            "item-b", "v2", "PREFERENCE", "response.language", "zh-CN", 2
        ),
    )
    result = api.evaluate_proposals(
        (proposal,),
        replace(state, current_values=current),
        ConservativeRequestTokenCounter(),
        capacity,
        now=1,
    )
    assert result[0].action == "CONFLICT_CANDIDATE"
    assert result[0].existing_item_ids == ("item-a", "item-b")
    assert result[0].index_status == "NOT_REQUESTED"
    assert result[0].source_dependencies == (source().source_ref,)


def test_dedup_and_replacement_intent_do_not_confirm_candidate():
    api, conflicts, state, capacity, proposal = fixture()
    current = (
        conflicts.CurrentFieldValue(
            "item-a", "v1", "PREFERENCE", "response.language", "en-US", 1
        ),
    )
    selected = replace(
        state, current_values=current, replacement_item_ids=frozenset({"item-a"})
    )
    result = api.evaluate_proposals(
        (proposal, proposal),
        selected,
        ConservativeRequestTokenCounter(),
        capacity,
        now=1,
    )
    assert len(result) == 1
    assert result[0].action == "REPLACE_CANDIDATE"
    assert result[0].decision_status == "PROPOSED"
    unchanged = proposal.model_copy(update={"value": "en-US"})
    assert (
        api.evaluate_proposals(
            (unchanged,), selected, ConservativeRequestTokenCounter(), capacity, now=1
        )[0].action
        == "NOOP"
    )


def test_model_fields_and_token_bounds_are_checked_before_creating_candidates():
    api, _, state, capacity, proposal = fixture()
    with pytest.raises(ValueError, match="PROPOSAL_FIELD_DENIED"):
        api.evaluate_proposals(
            (proposal.model_copy(update={"field_key": "candidate.impression"}),),
            state,
            ConservativeRequestTokenCounter(),
            capacity,
            now=1,
        )
    with pytest.raises(ValueError, match="PROPOSAL_COUNT_LIMIT"):
        api.evaluate_proposals(
            (proposal,) * 17, state, ConservativeRequestTokenCounter(), capacity, now=1
        )
