"""JD结构草案只保留可定位原句，不能自动采用或补充评分锚点。"""

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.contracts.hr import JdOutput


def test_jd_category_payloads_require_matching_dimensions_and_bounds():
    payload = {
        "candidates": [
            {
                "type": "EXPERIENCE",
                "dimension": "EXPERIENCE",
                "criterion": "3至5年开发经验",
                "source_quote": "3至5年开发经验",
                "experience": {"minimum_months": 36, "maximum_months": 60},
            }
        ]
    }
    result = JdOutput.model_validate(payload)
    assert result.candidates[0].experience.minimum_months == 36
    assert result.candidates[0].default_adopted is False
    payload["candidates"][0]["dimension"] = "SKILL"
    with pytest.raises(ValidationError):
        JdOutput.model_validate(payload)


def test_jd_requires_type_specific_payload_and_never_auto_adopts():
    candidate = {
        "type": "SKILL",
        "dimension": "SKILL",
        "criterion": "掌握Java",
        "source_quote": "掌握Java",
        "skill": {"name": "Java", "expected_level": 3, "importance": 8},
    }
    assert (
        JdOutput.model_validate({"candidates": [candidate]}).candidates[0].skill.name
        == "Java"
    )
    candidate["default_adopted"] = True
    with pytest.raises(ValidationError):
        JdOutput.model_validate({"candidates": [candidate]})
    candidate.pop("default_adopted")
    candidate["skill"]["importance"] = 11
    with pytest.raises(ValidationError):
        JdOutput.model_validate({"candidates": [candidate]})
    candidate["skill"] = None
    with pytest.raises(ValidationError):
        JdOutput.model_validate({"candidates": [candidate]})


def test_hard_condition_is_a_draft_and_unknown_values_are_not_guessed():
    candidate = {
        "type": "HARD_CONDITION",
        "dimension": "SKILL",
        "criterion": "必须掌握Java",
        "source_quote": "必须掌握Java",
        "hard_condition": {
            "type": "REQUIRED_SKILL",
            "values": ["Java"],
            "match_mode": "ALL",
        },
    }
    hard = (
        JdOutput.model_validate({"candidates": [candidate]})
        .candidates[0]
        .hard_condition
    )
    assert hard.threshold is None
    candidate["hard_condition"]["type"] = "AGE"
    with pytest.raises(ValidationError):
        JdOutput.model_validate({"candidates": [candidate]})
