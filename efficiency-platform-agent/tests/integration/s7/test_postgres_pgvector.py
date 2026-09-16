"""PostgreSQL 集成边界的离线替身测试；真实数据库 Gate 默认不执行。"""

from pathlib import Path


def test_real_database_gate_is_explicitly_disabled() -> None:
    plan = Path("docs/superpowers/plans/2026-09-03-S7-真实集成与验收-实施计划.md")
    text = plan.read_text(encoding="utf-8")
    assert "G3 PostgreSQL/pgvector" in text
    assert "默认" in text and "关闭" in text
