"""行业动态周报的离线接线验收。"""

from scripts.s7_verify import run_offline_scenario, verify


def test_industry_digest_offline_contains_evidence_and_no_external_io() -> None:
    result = run_offline_scenario("industry_digest")
    assert result["status"] == "SUCCEEDED"
    assert result["external_io"] is False
    assert result["evidence"]
    assert result["evidence"][0]["source_id"]


def test_missing_gate_is_not_executed_without_external_io() -> None:
    result = verify()
    assert result["status"] == "NOT_EXECUTED"
    assert result["external_io"] is False


def test_real_gate_rejects_malformed_authorization_without_external_io(
    tmp_path,
) -> None:
    approval_file = tmp_path / "authorization.json"
    approval_file.write_text('{"version":"wrong"}', encoding="utf-8")

    result = verify(gate="deepseek_chat", approval_file=approval_file)

    assert result["status"] == "NOT_EXECUTED"
    assert result["reason"] == "authorization_file_invalid"
    assert result["external_io"] is False
