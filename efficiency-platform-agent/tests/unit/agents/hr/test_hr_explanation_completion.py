"""扩展解释必须来自已确认判断与精确引用，不编造总结或凑核实点。"""

import json

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.contracts.hr import ExplanationOutput, HrSkillRequest
from efficiency_platform_agent.core.execution_control import RunControl
from tests.unit.agents.hr.test_hr_service import FakeAssembler, FakeProvider


def test_legacy_explanation_defaults_and_summary_bound():
    result = ExplanationOutput(highlights=[], gaps=[])
    assert (
        result.verification_points == []
        and result.quality_notes == []
        and result.summary == ""
    )
    with pytest.raises(ValidationError):
        ExplanationOutput(highlights=[], gaps=[], summary="字" * 81)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["summary", "quote"])
async def test_fabricated_summary_or_new_quote_does_not_pass_confirmed_evidence(tamper):
    item = {
        "text": "核实Java职责范围",
        "requirement_ids": ["r"],
        "evidence": [{"block_id": "b", "start": 0, "end": 4, "quote": "Java"}],
    }
    output = {
        "highlights": [],
        "gaps": [],
        "verification_points": [item],
        "quality_notes": [],
        "summary": "Java",
    }
    if tamper == "summary":
        output["summary"] = "管理100人团队"
    else:
        output["verification_points"][0]["evidence"][0]["quote"] = "Go语言"
    provider = FakeProvider([json.dumps(output, ensure_ascii=False)] * 3)
    request = HrSkillRequest(
        run_id="explanation",
        operation_id="explanation",
        blocks=[{"block_id": "b", "text": "Java"}],
        requirements=[{"requirement_id": "r", "criterion": "使用Java"}],
        assessments=[
            {
                "requirement_id": "r",
                "status": "MATCH",
                "reason": "Java",
                "evidence": [{"block_id": "b", "start": 0, "end": 4, "quote": "Java"}],
            }
        ],
    )
    with pytest.raises(ValueError, match="HR_EVALUATION_CONTRACT_FAILED"):
        await HrSkillService(FakeAssembler(ExplanationOutput), provider).execute(
            "hr.match.explain", request, RunControl()
        )
    assert provider.calls <= 3


@pytest.mark.asyncio
async def test_verified_points_and_extractive_summary_are_returned_without_filling_minimum():
    evidence = {"block_id": "b", "start": 0, "end": 4, "quote": "Java"}
    output = {
        "highlights": [],
        "gaps": [],
        "verification_points": [
            {
                "text": "核实Java职责范围",
                "requirement_ids": ["r"],
                "evidence": [evidence],
            }
        ],
        "quality_notes": [],
        "summary": "Java",
    }
    provider = FakeProvider([json.dumps(output, ensure_ascii=False)])
    request = HrSkillRequest(
        run_id="explanation-valid",
        operation_id="explanation-valid",
        blocks=[{"block_id": "b", "text": "Java"}],
        requirements=[{"requirement_id": "r", "criterion": "使用Java"}],
        assessments=[
            {
                "requirement_id": "r",
                "status": "MATCH",
                "reason": "Java",
                "evidence": [evidence],
            }
        ],
    )
    result = await HrSkillService(FakeAssembler(ExplanationOutput), provider).execute(
        "hr.match.explain", request, RunControl()
    )
    assert len(result["data"]["verification_points"]) == 1
    assert result["data"]["quality_notes"] == [] and result["data"]["summary"] == "Java"
    assert provider.calls == 1
