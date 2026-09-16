"""S7 人工验收与停用文档治理测试。"""

from pathlib import Path

ROOT = (
    Path(__file__).parents[2]
    / "docs"
    / "superpowers"
    / "sdd"
    / "operation-acceptance-s7"
)


def test_acceptance_report_contains_dual_status_and_gate_evidence() -> None:
    text = (ROOT / "S7阶段交付报告.md").read_text(encoding="utf-8")
    for term in (
        "IMPLEMENTATION_READY",
        "REAL_ACCEPTANCE_COMPLETE",
        "selected_real_gates",
        "清理回读",
    ):
        assert term in text
    assert "全 skipped" in text


def test_manual_contains_ten_dimensions_three_states_and_two_round_limit() -> None:
    text = (ROOT / "生产边界与停用手册.md").read_text(encoding="utf-8")
    assert text.count("评价维度") >= 1
    for term in ("通过", "需修改", "拒绝", "最多两轮", "G0"):
        assert term in text
    assert all(f"{i}." in text for i in range(1, 11))


def test_manual_requires_precise_cleanup_and_no_global_operations() -> None:
    text = (ROOT / "生产边界与停用手册.md").read_text(encoding="utf-8")
    for term in (
        "04-rollback.sql",
        "Schema",
        "Redis",
        "COS",
        "回读",
        "不得执行 FLUSHDB",
    ):
        assert term in text
