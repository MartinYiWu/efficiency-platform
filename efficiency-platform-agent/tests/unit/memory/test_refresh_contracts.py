"""刷新只改变原授权外壳，所有输入和回执均严格绑定原等待。"""

import copy
import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

FIXTURE = Path(__file__).parents[2] / "fixtures/memory_refresh_transport.json"


def models():
    return importlib.import_module("efficiency_platform_agent.contracts.memory_refresh")


def fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def parse(kind, raw):
    return getattr(models(), kind).model_validate_json(
        json.dumps(raw, ensure_ascii=False)
    )


def test_new_protocol_exists_with_shared_golden_fingerprint():
    data = fixture()
    resume = parse("MemoryContextResumeModel", data["resume"])
    assert resume.to_core().canonical_fingerprint() == data["canonical_resume_sha256"]
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    original = MemoryContextEnvelope.model_validate_json(
        json.dumps(data["original_context"])
    ).to_core()
    resume.to_core().validate_binding(
        wait, wait.scope, wait.execution_id, "d" * 64, original
    )
    assert (
        parse("MemoryContextResumeReceiptModel", data["receipt"])
        .to_core()
        .dispatch_allowed
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("new_content", True),
        ("new_content", 0),
        ("attempt", True),
        ("max_cost_cny", 1000),
        ("packet_revision", "1"),
        ("packet_revision", 1.0),
        ("mode", "REFRESH"),
        ("canonical_request_hmac", "c" * 63),
        ("resume_request_id", "😀" * 129),
        ("operation_hash", "x" * 64),
    ],
)
def test_resume_rejects_unknown_content_coercion_and_bad_identifiers(key, value):
    raw = fixture()["resume"] | {key: value}
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeModel", raw)


@pytest.mark.parametrize(
    "mode,context", [("refresh", None), ("cpu", "present"), ("paid", "present")]
)
def test_modes_cannot_smuggle_or_omit_new_context(mode, context):
    raw = fixture()["resume"]
    raw["mode"] = mode
    if context is None:
        raw["refreshed_context"] = None
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeModel", raw)


@pytest.mark.parametrize("mode", ["cpu", "paid"])
def test_non_refresh_requires_json_null_even_for_disabled_envelope(mode):
    raw = fixture()["resume"] | {
        "mode": mode,
        "refreshed_context": {
            "schema_version": "memory-context/1",
            "memory_mode": "DISABLED",
            "scope": None,
            "packet": None,
            "authorization": None,
        },
    }
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeModel", raw)


@pytest.mark.parametrize("key", list(fixture()["wait"]))
def test_wait_requires_explicit_fields_including_nulls(key):
    raw = fixture()["wait"]
    raw.pop(key)
    with pytest.raises(ValidationError):
        parse("MemoryContextWaitModel", raw)


@pytest.mark.parametrize(
    "change",
    [
        {"checkpoint_mode": "NONE"},
        {"checkpoint_id": None},
        {"wait_phase": "PREPARED", "canonical_request_hmac": None},
        {"stage_id": "stage"},
        {"refresh_count": 4},
        {"attempt": True},
        {"original_deadline": 1.5},
        {"stage_slot": -1},
    ],
)
def test_wait_rejects_inconsistent_phase_and_checkpoint(change):
    with pytest.raises(ValidationError):
        parse("MemoryContextWaitModel", fixture()["wait"] | change)


def test_before_prepare_and_none_are_explicit_and_nullable():
    raw = fixture()["wait"] | {
        "checkpoint_mode": "NONE",
        "checkpoint_ns": None,
        "checkpoint_id": None,
        "wait_phase": "BEFORE_PREPARE",
        "canonical_request_hmac": None,
    }
    assert parse("MemoryContextWaitModel", raw).to_core().canonical_request_hmac is None
    raw["canonical_request_hmac"] = "c" * 64
    with pytest.raises(ValidationError):
        parse("MemoryContextWaitModel", raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("wait_event_id", "other"),
        ("attempt", 2),
        ("logical_operation_id", "other"),
        ("canonical_request_hmac", None),
        ("operation_hash", "f" * 64),
        ("packet_revision", 2),
        ("expected_execution_revision", 2),
    ],
)
def test_binding_rejects_different_wait_anchor(field, value):
    data = fixture()
    raw = data["resume"] | {field: value}
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    with pytest.raises(ValueError):
        command = parse("MemoryContextResumeModel", raw).to_core()
        command.validate_binding(wait, wait.scope, wait.execution_id, "d" * 64, None)


@pytest.mark.parametrize(
    "dimension",
    [
        "tenant_id",
        "user_id",
        "domain",
        "top_level_agent_id",
        "session_kind",
        "session_id",
    ],
)
def test_full_route_scope_is_required(dimension):
    data = fixture()
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    scope = copy.deepcopy(data["wait"]["scope"])
    if dimension in {"domain", "top_level_agent_id"}:
        scope.update(domain="hr", top_level_agent_id="hr")
    elif dimension == "session_kind":
        scope.update(session_kind="TASK_ONLY", session_id=None)
    else:
        scope[dimension] = "other"
    from efficiency_platform_agent.core.memory import ConversationScope

    with pytest.raises(ValueError):
        parse("MemoryContextResumeModel", data["resume"]).to_core().validate_binding(
            wait, ConversationScope(**scope), wait.execution_id, "d" * 64, None
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("packet_id", "other"),
        ("execution_revision", 2),
        ("task_id", "other"),
        ("grant_epoch", 2),
        ("expires_at", 201),
        ("semantic_input_hash", "f" * 64),
    ],
)
def test_refreshed_context_must_preserve_original_context(field, value):
    data = fixture()
    command = parse("MemoryContextResumeModel", data["resume"]).to_core()
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    original = MemoryContextEnvelope.model_validate_json(
        json.dumps(data["original_context"])
    ).to_core()
    with pytest.raises(ValueError):
        changed = replace(
            command,
            refreshed_context=replace(
                command.refreshed_context,
                packet=replace(command.refreshed_context.packet, **{field: value}),
            ),
        )
        changed.validate_binding(
            wait, wait.scope, wait.execution_id, "d" * 64, original
        )


@pytest.mark.parametrize(
    "change",
    [
        {"candidate_phase": "UNKNOWN"},
        {"dispatch_allowed": False, "next_wait_event_id": "next"},
        {"candidate_phase": "PENDING"},
        {"state": "WAITING_CONTEXT"},
        {"current_packet_revision": 1},
        {"refresh_count": True},
        {"code": "MEMORY_RESUME_REJECTED"},
    ],
)
def test_receipt_rejects_inconsistent_success(change):
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeReceiptModel", fixture()["receipt"] | change)


def test_expired_receipts_preserve_technical_current_and_forbid_dispatch():
    raw = fixture()["receipt"] | {
        "code": "MEMORY_REFRESH_PACKET_EXPIRED",
        "dispatch_allowed": False,
        "candidate_phase": "EXPIRED_UNAPPLIED",
        "current_packet_revision": 1,
        "state": "WAITING_CONTEXT",
    }
    assert (
        parse("MemoryContextResumeReceiptModel", raw).to_core().current_packet_revision
        == 1
    )
    raw.update(
        candidate_phase="APPLIED_EXPIRED",
        current_packet_revision=3,
        next_wait_event_id="next",
    )
    assert (
        parse("MemoryContextResumeReceiptModel", raw).to_core().next_wait_event_id
        == "next"
    )
    raw.update(refresh_count=3, state="BLOCKED", next_wait_event_id=None)
    assert parse("MemoryContextResumeReceiptModel", raw).to_core().refresh_count == 3


def test_core_imports_only_core_and_standard_library():
    import ast

    path = (
        Path(__file__).parents[3]
        / "src/efficiency_platform_agent/core/memory_refresh.py"
    )
    assert path.exists(), "新增刷新核心协议尚未实现"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            assert not (node.module or "").startswith(
                (
                    "pydantic",
                    "efficiency_platform_agent.contracts",
                    "efficiency_platform_agent.security",
                )
            )


def test_nullable_cpu_paid_golden_roundtrip_preserves_every_required_null():
    data = fixture()
    wait = parse("MemoryContextWaitModel", data["nullable_wait"])
    assert json.loads(wait.model_dump_json()) == data["nullable_wait"]
    for key in ("cpu_resume", "paid_resume"):
        command = parse("MemoryContextResumeModel", data[key])
        assert json.loads(command.model_dump_json()) == data[key]
        assert command.to_core().canonical_fingerprint() == data[key + "_sha256"]
        command.to_core().validate_binding(
            wait.to_core(), wait.to_core().scope, wait.execution_id, "d" * 64, None
        )
    receipt = parse("MemoryContextResumeReceiptModel", data["cpu_receipt"])
    assert json.loads(receipt.model_dump_json()) == data["cpu_receipt"]


def test_unicode_128_identifier_is_valid_and_direct_core_rejects_bool_count():
    raw = fixture()["resume"] | {"resume_request_id": "😀" * 128}
    command = parse("MemoryContextResumeModel", raw).to_core()
    assert len(command.resume_request_id) == 128
    with pytest.raises(ValueError):
        replace(command, attempt=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "policy",
        "grant",
        "source_tuple",
        "item",
        "request",
        "semantic_digest",
        "deadline",
        "session",
        "fingerprint",
        "execution_route",
    ],
)
def test_no_context_field_beyond_approved_shell_can_change(mutation):
    from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope

    data = fixture()
    raw = copy.deepcopy(data["resume"])
    envelope = raw["refreshed_context"]
    if mutation == "policy":
        envelope["authorization"]["policy"]["max_paid_operations"] = 99
    elif mutation == "grant":
        envelope["authorization"]["execution_grants"][0]["purpose"] = "other"
    elif mutation == "source_tuple":
        envelope["packet"]["safety_dependencies"][0]["source_version"] = "other"
    elif mutation == "item":
        envelope["packet"]["items"][0]["value"] = "other"
    elif mutation == "request":
        envelope["authorization"]["request_digest"] = "f" * 64
    elif mutation == "semantic_digest":
        envelope["authorization"]["semantic_snapshot_digest"] = "f" * 64
    elif mutation == "deadline":
        envelope["authorization"]["deadline_epoch_seconds"] = 201
    elif mutation == "session":
        envelope["packet"]["scope"]["session_id"] = "other"
    elif mutation == "fingerprint":
        raw["expected_current_context_fingerprint"] = "f" * 64
    original = MemoryContextEnvelope.model_validate_json(
        json.dumps(data["original_context"])
    ).to_core()
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    with pytest.raises(ValueError):
        command = parse("MemoryContextResumeModel", raw).to_core()
        command.validate_binding(
            wait,
            wait.scope,
            "other" if mutation == "execution_route" else wait.execution_id,
            "d" * 64,
            original,
        )


@pytest.mark.parametrize(
    "change",
    [
        {
            "candidate_phase": "ACKED",
            "code": "SOURCE_CHANGED",
            "dispatch_allowed": False,
        },
        {
            "candidate_phase": None,
            "code": "MEMORY_REFRESH_PENDING",
            "state": "REFRESH_PENDING",
            "dispatch_allowed": False,
        },
        {
            "candidate_phase": "APPLIED_EXPIRED",
            "code": "MEMORY_REFRESH_PACKET_EXPIRED",
            "state": "WAITING_CONTEXT",
            "dispatch_allowed": False,
        },
    ],
)
def test_phase_and_code_cannot_describe_a_different_terminal(change):
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeReceiptModel", fixture()["receipt"] | change)


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("MemoryContextWaitModel", "attempt", 0),
        ("MemoryContextWaitModel", "attempt", 4),
        ("MemoryContextWaitModel", "expected_packet_revision", 0),
        ("MemoryContextWaitModel", "expected_execution_revision", 0),
        ("MemoryContextWaitModel", "original_deadline", 0),
        ("MemoryContextResumeModel", "attempt", 0),
        ("MemoryContextResumeModel", "attempt", 4),
        ("MemoryContextResumeModel", "packet_revision", 0),
        ("MemoryContextResumeModel", "expected_execution_revision", 0),
    ],
)
def test_original_operation_attempt_and_revisions_have_their_actual_domain(
    kind, key, value
):
    raw = fixture()["wait" if kind == "MemoryContextWaitModel" else "resume"] | {
        key: value
    }
    with pytest.raises(ValidationError):
        parse(kind, raw)


def test_official_graph_root_checkpoint_namespace_is_empty_and_not_none():
    raw = fixture()["wait"] | {"checkpoint_ns": ""}
    assert parse("MemoryContextWaitModel", raw).to_core().checkpoint_ns == ""
    with pytest.raises(ValidationError):
        parse("MemoryContextWaitModel", raw | {"checkpoint_ns": None})


def test_wait_exposes_exact_current_fingerprint_and_resume_cannot_use_another_wait_anchor():
    data = fixture()
    wait = parse("MemoryContextWaitModel", data["wait"]).to_core()
    assert wait.expected_current_context_fingerprint == "d" * 64
    with pytest.raises(ValidationError):
        parse(
            "MemoryContextWaitModel",
            data["wait"] | {"expected_current_context_fingerprint": "not-a-digest"},
        )
    changed_wait = replace(wait, expected_current_context_fingerprint="f" * 64)
    command = parse("MemoryContextResumeModel", data["cpu_resume"]).to_core()
    changed_wait = replace(
        changed_wait,
        wait_phase=importlib.import_module(
            "efficiency_platform_agent.core.memory_refresh"
        ).WaitPhase.BEFORE_PREPARE,
        canonical_request_hmac=None,
    )
    with pytest.raises(ValueError):
        command.validate_binding(
            changed_wait, wait.scope, wait.execution_id, "d" * 64, None
        )


@pytest.mark.parametrize(
    "field", ["packet_revision", "execution_revision", "current_packet_revision"]
)
def test_review_receipt_requires_positive_non_null_revision_even_for_unaccepted_failure(
    field,
):
    raw = fixture()["receipt"] | {
        "code": "SOURCE_CHANGED",
        "candidate_phase": None,
        "state": "BLOCKED",
        "dispatch_allowed": False,
        field: 0,
    }
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeReceiptModel", raw)


@pytest.mark.parametrize(
    "change",
    [
        {},
        {
            "code": "MEMORY_REFRESH_PENDING",
            "candidate_phase": "PENDING",
            "state": "REFRESH_PENDING",
            "dispatch_allowed": False,
            "current_packet_revision": 1,
        },
        {
            "code": "MEMORY_REFRESH_PACKET_EXPIRED",
            "candidate_phase": "EXPIRED_UNAPPLIED",
            "state": "WAITING_CONTEXT",
            "dispatch_allowed": False,
            "current_packet_revision": 1,
        },
        {
            "code": "MEMORY_REFRESH_PACKET_EXPIRED",
            "candidate_phase": "APPLIED_EXPIRED",
            "state": "WAITING_CONTEXT",
            "dispatch_allowed": False,
            "next_wait_event_id": "next",
        },
        {
            "code": "SOURCE_CHANGED",
            "candidate_phase": "ABORTED",
            "state": "REVOKED",
            "dispatch_allowed": False,
        },
    ],
)
def test_review_every_accepted_candidate_requires_one_consumed_attempt_and_positive_control(
    change,
):
    raw = fixture()["receipt"] | change | {"refresh_count": 0}
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeReceiptModel", raw)
    assert (
        parse("MemoryContextResumeReceiptModel", raw | {"refresh_count": 1})
        .to_core()
        .refresh_count
        == 1
    )


def test_review_applied_expired_successor_cannot_reuse_original_wait():
    raw = fixture()["receipt"]
    raw.update(
        code="MEMORY_REFRESH_PACKET_EXPIRED",
        candidate_phase="APPLIED_EXPIRED",
        state="WAITING_CONTEXT",
        dispatch_allowed=False,
        next_wait_event_id=raw["wait_event_id"],
    )
    with pytest.raises(ValidationError):
        parse("MemoryContextResumeReceiptModel", raw)
    assert (
        parse(
            "MemoryContextResumeReceiptModel",
            raw | {"next_wait_event_id": "different-wait"},
        )
        .to_core()
        .next_wait_event_id
        == "different-wait"
    )


@pytest.mark.parametrize(
    "code",
    ["CPU_CONFIRMED", "CONTINUATION_AUTH_UNSUPPORTED", "MEMORY_AUTHORITY_UNAVAILABLE"],
)
def test_review_unaccepted_receipt_preserves_null_unknown_revisions_and_zero_count(
    code,
):
    raw = fixture()["cpu_receipt"] | {
        "code": code,
        "receipt_ref": None,
        "wait_event_id": None,
        "packet_revision": None,
        "execution_revision": None,
        "current_packet_revision": None,
        "current_context_fingerprint": None,
        "refresh_count": 0,
    }
    assert parse("MemoryContextResumeReceiptModel", raw).to_core().refresh_count == 0


@pytest.mark.parametrize(
    "code",
    [
        "MEMORY_THREAD_FENCED",
        "MEMORY_REFRESH_AUTH_UNSUPPORTED",
        "MEMORY_AUTHORITY_REFRESH_REQUIRED",
        "UNKNOWN_LEGACY_CODE",
    ],
)
def test_review_python_v2_does_not_gain_legacy_codes(code):
    with pytest.raises(ValidationError):
        parse(
            "MemoryContextResumeReceiptModel", fixture()["cpu_receipt"] | {"code": code}
        )
