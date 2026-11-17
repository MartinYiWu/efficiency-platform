"""身份隔离保留职业事实，并覆盖JD到Provider的边界。"""

import hashlib
import json

import pytest

from efficiency_platform_agent.agents.hr.extraction import (
    extract_resume,
    model_safe_blocks,
)
from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.contracts.hr import (
    Block,
    ExplanationOutput,
    HrSkillRequest,
    InterviewOutput,
    JdOutput,
)
from efficiency_platform_agent.core.execution_control import RunControl
from tests.unit.agents.hr.test_hr_service import FakeAssembler, FakeProvider


def test_full_english_name_is_isolated_without_project_name_or_offset_loss():
    text = "Name: John Doe\nProject Name: Zephyr\nJohn Doe built Python services"
    raw = text.encode()
    result = extract_resume("resume.txt", raw, hashlib.sha256(raw).hexdigest())
    assert result.identity.name.value == "John Doe"
    evidence = result.identity.name.evidence[0]
    assert (evidence.start, evidence.end, evidence.quote) == (6, 14, "John Doe")
    assert result.cleaned_blocks[1].text == "Project Name: Zephyr"
    assert all(
        "John" not in b.text and "Doe" not in b.text for b in result.cleaned_blocks
    )
    for source, cleaned in zip(result.blocks, result.cleaned_blocks, strict=True):
        for offset in cleaned.offsets:
            assert (
                cleaned.text[offset.clean_start : offset.clean_end]
                == source.text[offset.source_start : offset.source_end]
            )


def test_model_sanitizer_anchors_name_label_to_field_line():
    text = "Name: John Doe\nProject Name: Zephyr\nJohn Doe built Python services"
    cleaned = model_safe_blocks([Block(block_id="b", text=text)])[0].text
    assert "John" not in cleaned and "Doe" not in cleaned
    assert "Project Name: Zephyr" in cleaned
    assert "built Python services" in cleaned
    assert len(cleaned) == len(text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("skill", "schema", "output"),
    [
        ("hr.jd.draft", JdOutput, {"candidates": []}),
        ("hr.match.explain", ExplanationOutput, {"highlights": [], "gaps": []}),
        (
            "hr.interview.generate",
            InterviewOutput,
            {"questions": [], "unfilled": [1, 2, 3, 4, 5, 6]},
        ),
    ],
)
async def test_jd_contact_values_never_reach_provider_messages(skill, schema, output):
    class InspectingProvider(FakeProvider):
        async def complete(self, request):
            messages = str(request.messages)
            assert "13812345678" not in messages
            assert "recruiter@example.com" not in messages
            assert "John Doe" not in messages
            assert "Project Name: Zephyr" in messages
            assert "Python services" in messages
            return await super().complete(request)

    provider = InspectingProvider([json.dumps(output)])
    request = HrSkillRequest(
        run_id="privacy",
        operation_id="privacy",
        maximum_attempts=1,
        jd_text="Name: John Doe\n13812345678 recruiter@example.com\nProject Name: Zephyr\nPython services",
        blocks=[Block(block_id="b", text="Python services")],
        requirements=[{"requirement_id": "r", "criterion": "Python services"}],
        assessments=[
            {
                "requirement_id": "r",
                "status": "UNKNOWN",
                "reason": "材料未提及",
                "evidence": [],
            }
        ],
    )
    result = await HrSkillService(FakeAssembler(schema), provider).execute(
        skill, request, RunControl()
    )
    assert result["data"] == schema.model_validate(output).model_dump(mode="json")
    assert request.jd_text.startswith("Name: John Doe")
    assert provider.calls == 1
