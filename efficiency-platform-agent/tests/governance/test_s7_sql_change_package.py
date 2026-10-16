"""Agent SQL 变更包治理测试。"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
PACK = ROOT / "sql" / "changes" / "20260903_001_S7验收命名空间"
PROMPT_PACK = ROOT / "sql" / "changes" / "20261016_001_Prompt资产多角色装配"
PROMPT_TABLES = {
    "agent_prompt_definition",
    "agent_prompt_version",
    "agent_prompt_message_template",
    "agent_prompt_variable",
    "agent_model_policy",
    "agent_output_contract",
    "agent_prompt_release",
    "agent_run_prompt_snapshot",
    "agent_prompt_test_case",
}


def test_sql_pack_contains_five_files_and_separated_responsibilities() -> None:
    expected = {
        "00-变更说明.md",
        "01-precheck.sql",
        "02-up.sql",
        "03-verify.sql",
        "04-rollback.sql",
    }
    assert {p.name for p in PACK.iterdir()} == expected
    precheck = (PACK / "01-precheck.sql").read_text(encoding="utf-8").lower()
    up = (PACK / "02-up.sql").read_text(encoding="utf-8").lower()
    verify = (PACK / "03-verify.sql").read_text(encoding="utf-8").lower()
    rollback = (PACK / "04-rollback.sql").read_text(encoding="utf-8").lower()
    assert "select" in precheck and "create table" not in precheck
    assert "create table" in up
    assert "select" in verify
    assert "drop schema" in rollback and "cascade" in rollback


def test_sql_pack_is_agent_only_and_never_creates_extension() -> None:
    forbidden = ("create extension", "business", "java_", "glimmer_")
    for path in PACK.glob("*.sql"):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(item in text for item in forbidden)
        assert "s7_acceptance_" in text


def test_change_note_has_authorization_and_rollback_placeholders() -> None:
    note = (PACK / "00-变更说明.md").read_text(encoding="utf-8")
    for term in ("预检", "影响", "验证", "回滚", "授权"):
        assert term in note


def test_prompt_asset_change_pack_is_complete_and_symmetric() -> None:
    expected_files = {
        "00-变更说明.md",
        "01-precheck.sql",
        "02-up.sql",
        "03-verify.sql",
        "04-rollback.sql",
    }
    assert {path.name for path in PROMPT_PACK.iterdir()} == expected_files

    precheck = (PROMPT_PACK / "01-precheck.sql").read_text(encoding="utf-8").lower()
    up = (PROMPT_PACK / "02-up.sql").read_text(encoding="utf-8").lower()
    verify = (PROMPT_PACK / "03-verify.sql").read_text(encoding="utf-8").lower()
    rollback = (PROMPT_PACK / "04-rollback.sql").read_text(encoding="utf-8").lower()

    assert "database()" in precheck
    assert "information_schema.tables" in precheck
    assert "create table" not in precheck
    assert "drop table" not in precheck

    for table in PROMPT_TABLES:
        assert f"create table {table}" in up
        assert table in verify
    assert "is_required tinyint" in up
    assert "is_sensitive tinyint" in up

    dropped_tables = set(
        re.findall(r"drop\s+table\s+if\s+exists\s+([a-z0-9_]+)", rollback)
    )
    assert dropped_tables == PROMPT_TABLES
    assert "drop database" not in rollback
    assert "drop schema" not in rollback
