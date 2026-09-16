"""S7 确定性质量指标回归测试。"""

import json
from pathlib import Path

DATASET = Path(__file__).parents[1] / "fixtures" / "s7" / "operation_cases_v1.jsonl"
MATRIX = (
    Path(__file__).parents[2]
    / "docs"
    / "superpowers"
    / "sdd"
    / "operation-acceptance-s7"
    / "需求到证据追踪矩阵.md"
)


def test_quality_metrics_meet_fixed_thresholds() -> None:
    cases = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line
    ]
    metrics = {key: value for case in cases for key, value in case["metrics"].items()}
    assert metrics["schema_required_fields"] == 1.0
    assert metrics["invalid_status"] == 0
    assert metrics["budget_tool_overreach"] == 0
    assert metrics["fact_source_linkage"] == 1.0
    assert metrics["duplicate_sources"] == 0
    assert metrics["partial_scope_completeness"] == 1.0
    assert metrics["cross_tenant_hits"] == 0
    assert metrics["unauthorized_external_calls"] == 0


def test_quality_matrix_records_thresholds_and_offline_boundary() -> None:
    text = MATRIX.read_text(encoding="utf-8")
    for term in ("十个", "Schema", "跨租户", "无外部 I/O", "IMPLEMENTATION_READY"):
        assert term in text
