"""多平台运营内容的离线接线验收。"""

from scripts.s7_verify import run_offline_scenario


def test_multi_platform_content_is_independent_per_platform() -> None:
    result = run_offline_scenario("multi_platform_content")
    outputs = result["deliverables"]
    assert set(outputs) == {"xiaohongshu", "wechat", "toutiao"}
    assert len(set(outputs.values())) == 3
    assert result["external_io"] is False
