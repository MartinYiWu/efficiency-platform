import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.hr import Fact


def test_measured_project_preserves_exact_source_and_scope():
    quote = "项目QPS 1250 request/second，主导，管理8人"
    fact = Fact(
        fact_id="p",
        kind="project",
        value=quote,
        evidence=[{"block_id": "b", "start": 0, "end": len(quote), "quote": quote}],
        measurement={
            "metric": "QPS",
            "unit": "request/second",
            "value": 1250,
            "project_id": "p",
            "role_level": 3,
            "managed_team_size": 8,
        },
    )
    assert fact.measurement.value == 1250


def test_numeric_claim_without_exact_source_is_rejected():
    with pytest.raises(ValidationError):
        Fact(
            fact_id="p",
            kind="project",
            value="参与项目",
            evidence=[{"block_id": "b", "start": 0, "end": 4, "quote": "参与项目"}],
            measurement={
                "metric": "QPS",
                "unit": "request/second",
                "value": 1250,
                "project_id": "p",
            },
        )
