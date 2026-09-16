"""S7 固定运营场景离线回归测试。"""

import json
from pathlib import Path

DATASET = Path(__file__).parents[1] / "fixtures" / "s7" / "operation_cases_v1.jsonl"


def _cases() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_dataset_has_ten_fixed_cases_covering_eight_scenarios() -> None:
    cases = _cases()
    assert len(cases) == 10
    scenarios = {case["scenario_id"] for case in cases}
    assert len(scenarios) == 8
    assert {case["external_io"] for case in cases} == {False}


def test_cases_are_deterministic_and_forbid_side_effect_capabilities() -> None:
    cases = _cases()
    assert len({case["case_id"] for case in cases}) == len(cases)
    forbidden = {"publish", "send", "transaction", "platform_post"}
    for case in cases:
        assert not (forbidden & set(case.get("capabilities", [])))
        assert case["fixture_kind"] == "固定Stub"
    complete = next(case for case in cases if case["case_id"] == "case-multi-platform")
    assert len(complete["platform_outputs"]) == len(set(complete["platform_outputs"]))


def test_partial_and_unavailable_cases_expose_complete_scope() -> None:
    by_id = {case["case_id"]: case for case in _cases()}
    assert by_id["case-search-unavailable"]["status"] == "PARTIAL"
    assert by_id["case-specialist-failed"]["status"] == "PARTIAL"
    assert by_id["case-upload-review"]["status"] == "DATA_UNAVAILABLE"
    for case in by_id.values():
        assert case["completed_scope"]
        assert case["missing_scope"] is not None
