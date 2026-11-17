"""精确引用不能为受保护属性推断提供后门，违反输出必须失败而非负面结论。"""

import json

import pytest

from efficiency_platform_agent.agents.hr.evaluation import validate_assessments
from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.contracts.hr import (
    Assessment,
    Block,
    EvaluationOutput,
    ExplanationOutput,
    HrSkillRequest,
    Requirement,
)
from efficiency_platform_agent.core.execution_control import RunControl
from tests.unit.agents.hr.test_hr_service import FakeAssembler, FakeProvider


@pytest.mark.parametrize("reason", ["年龄偏大不适合", "性别决定协作能力"])
def test_protected_reason_is_rejected_even_with_an_exact_real_quote(reason):
    assessment = Assessment(
        requirement_id="r",
        status="MATCH",
        reason=reason,
        evidence=[{"block_id": "b", "start": 0, "end": 4, "quote": "Java"}],
    )
    with pytest.raises(ValueError, match="PROTECTED"):
        validate_assessments(
            [Requirement(requirement_id="r", criterion="Java")],
            [assessment],
            [Block(block_id="b", text="Java")],
        )


def test_unknown_not_mentioned_remains_valid_without_evidence():
    validate_assessments(
        [Requirement(requirement_id="r", criterion="Java")],
        [
            Assessment(
                requirement_id="r",
                status="UNKNOWN",
                reason="材料未提及，保留待核验",
                evidence=[],
            )
        ],
        [Block(block_id="b", text="Java")],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["reason", "verification", "summary"])
async def test_unsafe_model_text_fails_contract_inside_same_one_attempt_operation(kind):
    evidence = {"block_id": "b", "start": 0, "end": 4, "quote": "Java"}
    assessment = {
        "requirement_id": "r",
        "status": "MATCH",
        "reason": "Java",
        "evidence": [evidence],
    }
    if kind == "reason":
        output = {"assessments": [dict(assessment, reason="年龄偏大")]}
        schema = EvaluationOutput
        skill = "hr.requirements.evaluate"
    else:
        output = {
            "highlights": [],
            "gaps": [],
            "verification_points": [
                {"text": "性别推断", "requirement_ids": ["r"], "evidence": [evidence]}
            ]
            if kind == "verification"
            else [],
            "summary": "年龄" if kind == "summary" else "",
        }
        schema = ExplanationOutput
        skill = "hr.match.explain"
    request = HrSkillRequest(
        run_id="protected",
        operation_id="protected",
        maximum_attempts=1,
        blocks=[{"block_id": "b", "text": "Java"}],
        requirements=[{"requirement_id": "r", "criterion": "Java"}],
        assessments=[assessment],
    )
    provider = FakeProvider([json.dumps(output, ensure_ascii=False)])
    with pytest.raises(ValueError, match="HR_EVALUATION_CONTRACT_FAILED"):
        await HrSkillService(FakeAssembler(schema), provider).execute(
            skill, request, RunControl()
        )
    assert provider.calls == 1
