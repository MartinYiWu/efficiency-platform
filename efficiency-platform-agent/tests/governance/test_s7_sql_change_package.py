"""S7 PostgreSQL SQL 变更包治理测试。"""

from pathlib import Path

ROOT = Path(__file__).parents[2]
PACK = ROOT / "sql" / "changes" / "20260903_001_S7验收命名空间"


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
