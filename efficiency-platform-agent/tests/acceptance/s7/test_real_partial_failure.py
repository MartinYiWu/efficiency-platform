"""部分失败场景的离线接线验收。"""

from scripts.s7_verify import run_offline_scenario


def test_partial_failure_exposes_completed_and_missing_scope() -> None:
    result = run_offline_scenario("partial_failure")
    assert result["status"] == "PARTIAL"
    assert result["completed_scope"]
    assert result["missing_scope"]
    assert result["external_io"] is False
