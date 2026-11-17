"""RF02 离线结构合同；真实约束行为须独立 SQL 评审后在隔离库验证。"""

import re
from pathlib import Path

import pytest

from efficiency_platform_agent.core.memory_refresh import (
    CandidatePhase,
    RefreshRecordKind,
    ResumeCode,
    WaitPhase,
)

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "efficiency-platform-agent/sql/bootstrap"
JAVA = ROOT / "ai-efficiency-platform/sql"
MYSQL = AGENT / "memory_context_refresh_v1"
PG = AGENT / "memory_thread_refresh_v1"
JUP = JAVA / "migration/V1.2.18__memory_context_refresh.sql"
FILES = (
    "00-变更说明.md",
    "01-precheck.sql",
    "02-up.sql",
    "03-verify.sql",
    "04-rollback.sql",
)


def sql(path: Path) -> str:
    assert path.is_file(), f"缺少 RF02 资产：{path.relative_to(ROOT)}"
    return re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8")).lower()


@pytest.mark.parametrize("pack", [MYSQL, PG])
def test_new_package_has_five_separated_assets(pack: Path) -> None:
    assert pack.is_dir(), f"缺少 RF02 增量包：{pack.name}"
    assert {p.name for p in pack.iterdir()} == set(FILES)
    for name in ("01-precheck.sql", "03-verify.sql"):
        text = sql(pack / name)
        assert "select" in text
        assert not re.search(
            r"\b(create|alter|drop|insert|update|delete|set|call)\b", text
        )


def test_original_fingerprint_survives_current_backfill() -> None:
    text = sql(MYSQL / "02-up.sql")
    assert "add column current_context_fingerprint" in text
    assert "set current_context_fingerprint=context_fingerprint" in text
    assert "modify current_context_fingerprint char(64)" in text
    assert "new.current_context_fingerprint<=>old.current_context_fingerprint" in text
    assert not re.search(r"\b(drop|modify)\s+(column\s+)?context_fingerprint\b", text)
    assert "drop trigger trg_memory_execution_scrub" not in text


def test_journal_identity_is_kind_namespaced_and_result_unique() -> None:
    text = re.sub(r"\s+", "", sql(MYSQL / "02-up.sql"))
    assert "primarykey(tenant_id,execution_id,record_kind,record_id)" in text
    assert (
        "uniquekeyuk_memory_refresh_result(tenant_id,execution_id,result_operation_id,result_attempt)"
        in text
    )
    for kind in RefreshRecordKind:
        assert f"'{kind.value.lower()}'" in text
    assert "fk_memory_refresh_executionforeignkey(tenant_id,execution_id)" in text


def test_journal_freezes_wait_cas_and_real_checkpoint_before_ready() -> None:
    text = sql(MYSQL / "02-up.sql")
    assert "expected_current_context_fingerprint" in text
    for phase in WaitPhase:
        assert f"'{phase.value.lower()}'" in text
    assert "'building'" in text and "'ready'" in text
    assert "checkpoint_ns is not null" in text
    assert "octet_length(checkpoint_id)>0" in text
    assert "octet_length(checkpoint_ns)>0" not in text
    assert "canonical_request_hmac is null" in text
    assert "attempt between 1 and 3" in text
    assert "stage_slot between 1 and 3" in text


def test_refresh_snapshot_requires_local_matching_journal_and_keeps_scrub() -> None:
    text = sql(MYSQL / "02-up.sql")
    for term in (
        "trg_memory_execution_refresh",
        "'snapshot_applied'",
        "'active'",
        "'revoked'",
        "'scrubbed'",
        "memory_refresh_journal_required",
    ):
        assert term in text
    assert "new.snapshot_ciphertext is null" in text
    assert "new.snapshot_nonce is null" in text
    assert "new.current_context_fingerprint<=>old.current_context_fingerprint" in text
    assert "agent_memory_thread_execution" not in text


def test_journal_terminal_body_and_resume_start_cannot_resurrect() -> None:
    text = sql(MYSQL / "02-up.sql")
    for term in (
        "memory_refresh_phase_regression",
        "memory_refresh_body_resurrection",
        "memory_refresh_terminal_immutable",
        "memory_refresh_next_wait_immutable",
        "memory_refresh_resume_start_regression",
        "memory_refresh_scrub_proof_required",
    ):
        assert term in text
    assert "'captured'" in text
    assert "'claimed'" in text and "'done'" in text
    assert "unique key uk_memory_refresh_open_wait" in text
    assert "unique key uk_memory_refresh_pending" in text


def test_pg_preserves_old_counter_receipts_and_fences_pending() -> None:
    text = sql(PG / "02-up.sql")
    for phase in CandidatePhase:
        assert f"'{phase.value.lower()}'" in text
    assert "'waiting_context'" in text and "'refresh_pending'" in text
    assert "refresh_count<old.refresh_count" in text
    assert "refresh_count>3" in text
    assert "'resume'" in text and "'erasure'" in text
    assert "memory_refresh_terminal_immutable" in text
    assert not re.search(r"set\s+refresh_count\s*=\s*0", text)
    assert "drop table agent_memory_thread_resume" not in text


def test_nullable_legacy_discriminator_cannot_bypass_v2_shape() -> None:
    text = sql(PG / "02-up.sql")
    assert "record_kind is not null and record_kind='resume'" in text
    assert "authorization_binding is not null and authorization_binding='acked'" in text
    assert (
        "authorization_binding is not null and authorization_binding='align_only'"
        in text
    )
    text = sql(MYSQL / "02-up.sql")
    assert "record_kind<>'refresh' and candidate_phase is null" in text
    assert "refresh_count=pg_ordinal" in text


def test_three_domains_keep_exact_frozen_receipt_code_whitelist() -> None:
    for path, constraint in (
        (JUP, "ck_memory_packet_refresh_code"),
        (MYSQL / "02-up.sql", "ck_memory_refresh_receipt_code"),
        (PG / "02-up.sql", "ck_memory_thread_resume_code"),
    ):
        match = re.search(
            rf"constraint {constraint} check\([^\n]*? in \(([^)]+)\)\)", sql(path)
        )
        assert match is not None
        assert set(re.findall(r"'([^']+)'", match[1])) == {
            code.value.lower() for code in ResumeCode
        }


def test_review_mysql_resume_start_uses_null_safe_edges() -> None:
    text = sql(MYSQL / "02-up.sql")
    for before, after in (("ready", "claimed"), ("claimed", "done")):
        assert f"old.resume_start<=>'{before}'" in text
        assert f"new.resume_start<=>'{after}'" in text
    assert "new.resume_start<=>'ready'" in text
    assert "old.resume_start='" not in text
    assert "new.resume_start='" not in text


def test_review_graph_building_can_abort_without_inventing_checkpoint() -> None:
    text = sql(MYSQL / "02-up.sql")
    assert (
        "phase in ('building','aborted') and checkpoint_ns is null and checkpoint_id is null"
        in text
    )
    assert "old.phase<>'building' or new.phase<>'ready'" in text


@pytest.mark.parametrize(
    "path,field",
    [
        (JUP, "receipt_code"),
        (MYSQL / "02-up.sql", "receipt_code"),
        (PG / "02-up.sql", "result_code"),
    ],
)
def test_review_aborted_cannot_steal_exclusive_phase_codes(
    path: Path, field: str
) -> None:
    text = sql(path)
    branches = re.findall(
        rf"phase='aborted' and [^\n]*?{field} not in \(([^)]+)\)", text
    )
    assert branches
    excluded = set(re.findall(r"'([^']+)'", branches[-1]))
    assert {
        "context_refreshed",
        "memory_refresh_pending",
        "memory_refresh_packet_expired",
        "cpu_confirmed",
        "continuation_auth_unsupported",
    } <= excluded


def test_review_pg_successor_wait_keeps_phase_and_before_wait_ready() -> None:
    text = sql(PG / "02-up.sql")
    assert (
        "new.wait_phase is distinct from old.wait_phase or new.wait_phase is distinct from r.wait_phase"
        in text
    )
    assert "r.candidate_phase='expired_unapplied' and (new.wait_status<>'ready'" in text


def test_review_pg_legacy_cannot_claim_candidate_results() -> None:
    text = sql(PG / "02-up.sql")
    assert "ck_memory_thread_resume_legacy_code" in text
    assert (
        "record_kind is not null or result_code not in ('context_refreshed','memory_refresh_pending','memory_refresh_packet_expired')"
        in text
    )


def test_review_pg_erasure_exception_requires_complete_namespace() -> None:
    text = sql(PG / "02-up.sql")
    for term in (
        "legacy_erasure boolean := false",
        "jsonb_typeof(legacy_key)='array'",
        "jsonb_array_length(legacy_key)=3",
        "legacy_key->>0='memory-thread-receipt/2'",
        "legacy_key->>1='erasure'",
        "jsonb_typeof(legacy_key->2)='string'",
        "length(legacy_key->>2)>0",
        "if legacy_erasure is not true",
    ):
        assert term in text
    precheck = sql(PG / "01-precheck.sql")
    assert "jsonb_array_length(resume_request_id::jsonb)=3" in precheck
    assert "resume_request_id::jsonb->>0='memory-thread-receipt/2'" in precheck


@pytest.mark.parametrize("name", ["01-precheck.sql", "03-verify.sql"])
def test_review_mysql_introspection_covers_defaults_and_context_contracts(
    name: str,
) -> None:
    text = sql(MYSQL / name)
    assert "column_default" in text and "character_set_name" in text
    checks = next(
        line
        for line in text.splitlines()
        if "information_schema.table_constraints" in line
    )
    foreign = next(
        line
        for line in text.splitlines()
        if "information_schema.key_column_usage" in line
    )
    for table in ("agent_context_operation", "agent_context_manifest"):
        assert table in checks and table in foreign
    java_name = "precheck" if name.startswith("01") else "verify"
    assert "column_default" in sql(
        JAVA / f"verification/V1.2.18__{java_name}_memory_context_refresh.sql"
    )


@pytest.mark.parametrize("name", ["01-precheck.sql", "03-verify.sql"])
def test_review_pg_introspection_covers_four_tables_and_all_delta(name: str) -> None:
    text = sql(PG / name)
    columns = next(
        line for line in text.splitlines() if "information_schema.columns" in line
    )
    assert (
        "agent_memory_thread_member" in columns
        and "agent_memory_thread_namespace" in columns
    )
    if name.startswith("01"):
        for term in (
            "wait_checkpoint_id",
            "terminal_reason",
            "authorization_binding",
            "pg_proc",
            "pg_trigger",
            "existing_delta_indexes",
        ):
            assert term in text


def test_native_mysql_same_table_trigger_reads_use_shared_current_locks() -> None:
    same_table_reads = 0
    for path in (JUP, MYSQL / "02-up.sql"):
        text = sql(path)
        triggers = re.findall(
            r"create trigger [a-z_]+ before (?:insert|update|delete) on ([a-z_]+) for each row[^\n]*\n(.*?)\nend\$\$",
            text,
            re.DOTALL,
        )
        assert triggers
        for table, body in triggers:
            for line in body.splitlines():
                if re.search(rf"\bfrom {table}\b", line):
                    same_table_reads += 1
                    assert "lock in share mode" in line
                    assert "for update" not in line
    assert same_table_reads == 6
    assert re.search(r"from ai_memory_packet where[^\n]+for update", sql(JUP))
    assert re.search(
        r"from agent_memory_execution where[^\n]+for update", sql(MYSQL / "02-up.sql")
    )


def test_old_bootstraps_lack_delta_and_are_not_replaced() -> None:
    assert "current_context_fingerprint" not in sql(
        AGENT / "memory_execution_v1/02-up.sql"
    )
    assert "trg_memory_execution_scrub" in sql(
        AGENT / "memory_execution_scrub_v1/02-up.sql"
    )
    assert "waiting_context" not in sql(AGENT / "memory_thread_v1/02-up.sql")
    assert "checkpoint_mode" in sql(AGENT / "memory_thread_capability_v1/02-up.sql")


def test_java_anchor_is_original_session_bound_and_candidates_append_only() -> None:
    text = sql(JUP)
    for term in (
        "ai_memory_packet_refresh",
        "original_session_ref",
        "policy_ttl_seconds",
        "source_retention_deadline",
        "original_deadline",
        "'anchor'",
        "'refresh'",
        "'prepared'",
        "'applied_expired'",
        "memory_refresh_anchor_immutable",
        "memory_refresh_terminal_immutable",
        "memory_refresh_candidate_limit",
    ):
        assert term in text
    assert "foreign key(tenant_id,execution_id)" in text
    assert (
        "unique key uk_memory_packet_refresh_revision(tenant_id,packet_id,target_revision)"
        in text
    )
    assert "update ai_memory_packet " not in text


@pytest.mark.parametrize(
    "path",
    [
        MYSQL / "04-rollback.sql",
        PG / "04-rollback.sql",
        JAVA / "rollback/R__V1.2.18__memory_context_refresh.sql",
    ],
)
def test_rollback_hard_refuses_used_semantics_before_removing_protection(
    path: Path,
) -> None:
    text = sql(path)
    failure = min(
        i
        for term in ("signal sqlstate", "raise exception")
        if (i := text.find(term)) >= 0
    )
    destructive = min(
        i
        for term in ("drop trigger", "drop table", "drop column")
        if (i := text.find(term)) >= 0
    )
    assert failure < destructive
    assert "rollback_requires_unused" in text


@pytest.mark.parametrize("name", ["precheck", "verify"])
def test_java_readonly_assets_inspect_definitions(name: str) -> None:
    text = sql(JAVA / f"verification/V1.2.18__{name}_memory_context_refresh.sql")
    assert "information_schema" in text
    assert not re.search(r"\b(create|alter|drop|insert|update|delete|set|call)\b", text)
