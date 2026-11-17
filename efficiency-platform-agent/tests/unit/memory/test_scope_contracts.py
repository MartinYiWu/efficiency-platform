from dataclasses import FrozenInstanceError, replace

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.memory import (
    ConversationScopeModel,
    MemoryProposalModel,
)
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    ExecutionScope,
    MemoryProposal,
    MemoryReference,
)


def scope():
    return ConversationScope(
        "tenant", "user", "operations", "operations", "CONVERSATION", "session"
    )


def test_history_key_has_all_five_identity_fields():
    original = scope()
    assert original.history_key == (
        "tenant",
        "user",
        "operations",
        "operations",
        "session",
    )
    for field in ("tenant_id", "user_id", "session_id"):
        assert replace(original, **{field: "other"}).history_key != original.history_key
    assert (
        replace(original, domain="hr", top_level_agent_id="hr").history_key
        != original.history_key
    )
    with pytest.raises(FrozenInstanceError):
        original.user_id = "other"


def test_task_only_never_has_history():
    assert (
        ConversationScope("t", "u", "hr", "hr", "TASK_ONLY", None).history_key is None
    )
    for kind, session in [
        ("TASK_ONLY", "s"),
        ("CONVERSATION", None),
        ("CONVERSATION", ""),
        ("unknown", "s"),
    ]:
        with pytest.raises(ValueError, match="SCOPE_"):
            replace(scope(), session_kind=kind, session_id=session)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", ""),
        ("user_id", " " * 2),
        ("tenant_id", "x" * 129),
        ("domain", "admin"),
        ("top_level_agent_id", "admin"),
    ],
)
def test_invalid_identity_rejected_without_echo(field, value):
    with pytest.raises(ValueError) as error:
        replace(scope(), **{field: value})
    assert value not in str(error.value) if value.strip() else True


def test_execution_scope_requires_all_ids():
    execution = ExecutionScope(
        scope(), "task", "execution", "subtask", "answer", "general_chat"
    )
    with pytest.raises(ValueError):
        replace(execution, execution_agent_id="")
    with pytest.raises(ValueError):
        replace(execution, subtask_id="")


def test_boundary_roundtrip_and_model_cannot_forge_governance():
    boundary = ConversationScopeModel.from_core(scope())
    assert boundary.to_core() == scope()
    with pytest.raises(ValidationError):
        ConversationScopeModel(**{**boundary.model_dump(), "permissions": ["all"]})
    for name in (
        "scope",
        "confirmed_by",
        "budget",
        "allowed_agent_ids",
        "safety_dependencies",
    ):
        with pytest.raises(ValidationError):
            MemoryProposalModel(
                kind="PREFERENCE",
                field_key="response.language",
                value="zh-CN",
                **{name: "forged"},
            )
    with pytest.raises(ValidationError):
        MemoryProposalModel(
            kind="PREFERENCE",
            field_key="response.language",
            value="zh-CN",
            safety_dependencies=(),
        )


def test_private_values_are_not_repr_and_error_does_not_echo():
    private = "private-body-secret"
    assert private not in repr(
        MemoryProposal("PREFERENCE", "response.language", private)
    )
    assert private not in repr(
        MemoryReference("item", "1", "response.language", private)
    )
    with pytest.raises(ValidationError) as error:
        MemoryProposalModel(kind=private, field_key="response.language", value=private)
    assert private not in str(error.value)


def test_proposal_kind_and_policy_scopes_are_enumerated():
    from efficiency_platform_agent.core.memory import MemoryPolicy

    with pytest.raises(ValueError):
        MemoryProposal("UNKNOWN", "response.language", "zh")
    with pytest.raises(ValueError):
        MemoryPolicy(
            "policy", "1", "hr", frozenset({"hr"}), allowed_scopes=frozenset({"GLOBAL"})
        )


def test_nested_mutable_values_are_rejected():
    with pytest.raises((TypeError, ValueError)):
        MemoryReference("item", "1", "response.language", "zh", [])
    with pytest.raises(ValidationError):
        MemoryProposalModel(
            kind="PREFERENCE", field_key="response.language", value={"secret": "body"}
        )
