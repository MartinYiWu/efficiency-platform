"""节选回答 Prompt 种子仅创建新草稿，回滚不得删除已发布历史。"""

import re
from pathlib import Path

SQL = Path(__file__).resolve().parents[3] / "ai-efficiency-platform/sql"


def test_answer_prompt_seed_is_new_draft_only_with_nonconflicting_ids():
    seed_path = SQL / "seed/V1.1.8__customer_service_answer_evidence_scope.sql"
    seed = seed_path.read_text(encoding="utf-8")
    assert "customer_service.evidence_scope.v1" in seed
    for text in (
        "FULL_PARENT",
        "EXTRACTED_SPANS",
        "不得推断未提供",
        "supporting_chunk_ids",
        "citation_type",
        "修复",
    ):
        assert text in seed
    assert seed.count("'DRAFT'") == 3
    assert "'PUBLISHED'" not in seed
    assert "UPDATE ai_prompt" not in seed
    assert "INSERT INTO ai_agent_version_prompt_binding" not in seed
    ids = set(
        re.findall(r"[345][01]000000-0000-0000-0000-0000000010(?:09|10|14)", seed)
    )
    assert len(ids) == 12
    for path in (*SQL.glob("migration/*.sql"), *SQL.glob("seed/*.sql")):
        if path != seed_path:
            assert not any(value in path.read_text(encoding="utf-8") for value in ids)


def test_answer_prompt_change_has_readonly_precheck_verify_and_guarded_rollback():
    precheck = (
        SQL / "manual/M__1.1.8__customer_service_answer_evidence_scope_precheck.sql"
    ).read_text(encoding="utf-8")
    verify = (
        SQL / "verification/V1.1.8__verify_customer_service_answer_evidence_scope.sql"
    ).read_text(encoding="utf-8")
    rollback = (
        SQL / "rollback/R__V1.1.8__customer_service_answer_evidence_scope.sql"
    ).read_text(encoding="utf-8")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE)\b", precheck + verify)
    assert "ai_agent_version_prompt_binding" in precheck + verify
    assert "customer_service.evidence_scope.v1" in verify
    assert "status='DRAFT'" in rollback
    assert "NOT EXISTS" in rollback
    assert "ai_agent_version_prompt_binding" in rollback
    assert "DELETE FROM ai_prompt_definition" not in rollback
