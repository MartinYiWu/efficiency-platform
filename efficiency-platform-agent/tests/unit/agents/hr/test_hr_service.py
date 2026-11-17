import pytest

from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.contracts.hr import HrSkillRequest
from efficiency_platform_agent.core.execution_control import RunControl


@pytest.mark.asyncio
async def test_skill_missing_configuration_and_stopped_run_never_call():
    service = HrSkillService(None, None)
    request = HrSkillRequest(run_id="r", operation_id="o")
    with pytest.raises(ValueError, match="HR_CONFIG"):
        await service.execute("hr.resume.structure", request, RunControl())
    control = RunControl()
    control.stop()
    with pytest.raises(Exception, match="任务已停止"):
        await service.execute("hr.jd.draft", request, control)


@pytest.mark.asyncio
async def test_model_requests_reject_identity_before_provider():
    from efficiency_platform_agent.agents.hr.extraction import model_safe_blocks
    from efficiency_platform_agent.contracts.hr import Block

    blocks = model_safe_blocks(
        [
            Block(block_id="a", text="姓名：张三\n性别：男\nPython"),
            Block(block_id="b", text="张三 手机13812345678"),
        ]
    )
    assert all(
        "张三" not in b.text and "13812345678" not in b.text and "男" not in b.text
        for b in blocks
    )
    assert "Python" in blocks[0].text


class FakeAssembler:
    def __init__(self, output_type):
        self.output_type = output_type
        self.inputs = []

    async def assemble(self, **kwargs):
        from types import SimpleNamespace

        from efficiency_platform_agent.prompts.contracts import PromptMessage

        self.inputs.append(kwargs)
        return SimpleNamespace(
            model_policy=SimpleNamespace(
                max_input_tokens=131072,
                max_output_tokens=4096,
                max_retries=2,
                model_name="fake",
                temperature=0.0,
                read_timeout_ms=1000,
            ),
            messages=(
                PromptMessage("SYSTEM", "已发布指令"),
                PromptMessage(
                    "USER",
                    __import__("json").dumps(
                        kwargs["variables"]["input_json"].value, ensure_ascii=False
                    ),
                ),
            ),
            output_contract=SimpleNamespace(
                json_schema=self.output_type.model_json_schema()
            ),
        )


class FakeProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = 0

    async def complete(self, request):
        from efficiency_platform_agent.core.execution_control import (
            consume_http_attempt,
        )
        from efficiency_platform_agent.core.run import (
            ProviderMessage,
            ProviderResult,
            ProviderUsage,
        )

        consume_http_attempt()
        self.calls += 1
        return ProviderResult(
            "provider-result/1",
            ProviderMessage("assistant", next(self.outputs)),
            ProviderUsage(1, 1, 0, 0, 0),
        )


@pytest.mark.asyncio
async def test_semantic_skill_real_provider_port_and_evidence_repair_share_operation():
    from efficiency_platform_agent.contracts.hr import EvaluationOutput

    assembler = FakeAssembler(EvaluationOutput)
    provider = FakeProvider(
        [
            "{}",
            '{"assessments":[{"requirement_id":"a","status":"MATCH","reason":"明确","evidence":[{"block_id":"b","start":0,"end":6,"quote":"Python"}]}]}',
        ]
    )
    service = HrSkillService(assembler, provider)
    control = RunControl()
    request = HrSkillRequest(
        run_id="r",
        operation_id="o",
        blocks=[{"block_id": "b", "text": "Python"}],
        requirements=[{"requirement_id": "a", "criterion": "Python"}],
    )
    result = await service.execute("hr.requirements.evaluate", request, control)
    assert result["data"]["assessments"][0]["status"] == "MATCH"
    assert control.calls == 2
    assert len(control.operations) == 1
    assert all(o.attempts == 2 for o in control.operations.values())
    replay = await service.execute("hr.requirements.evaluate", request, control)
    assert replay == result and provider.calls == 2
    control.stop()
    with pytest.raises(Exception, match="任务已停止"):
        await service.execute("hr.requirements.evaluate", request, control)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_three_bad_outputs_fail_without_negative_candidate_result():
    from efficiency_platform_agent.contracts.hr import FactOutput

    provider = FakeProvider(["{}"] * 3)
    service = HrSkillService(FakeAssembler(FactOutput), provider)
    control = RunControl()
    with pytest.raises(ValueError, match="HR_EVALUATION_CONTRACT_FAILED"):
        await service.execute(
            "hr.resume.structure", HrSkillRequest(run_id="r", operation_id="o"), control
        )
    assert provider.calls == 3 and control.stopped


@pytest.mark.asyncio
async def test_large_resume_is_split_before_model_and_merged_without_model_merge():
    from efficiency_platform_agent.contracts.hr import FactOutput

    provider = FakeProvider(['{"facts":[]}'] * 12)
    assembler = FakeAssembler(FactOutput)
    service = HrSkillService(assembler, provider)
    request = HrSkillRequest(
        run_id="r",
        operation_id="o",
        blocks=[{"block_id": str(i), "text": "开发工作。" * 1500} for i in range(10)],
    )
    result = await service.execute("hr.resume.structure", request, RunControl())
    assert result["data"]["facts"] == []
    assert 1 < provider.calls <= 12
    assert len(assembler.inputs) == provider.calls


@pytest.mark.asyncio
async def test_same_operation_changed_input_is_rejected_not_stale_replayed():
    from efficiency_platform_agent.contracts.hr import FactOutput

    service = HrSkillService(FakeAssembler(FactOutput), FakeProvider(['{"facts":[]}']))
    control = RunControl()
    request = HrSkillRequest(
        run_id="r", operation_id="o", blocks=[{"block_id": "a", "text": "Python"}]
    )
    await service.execute("hr.resume.structure", request, control)
    with pytest.raises(ValueError, match="HR_EVALUATION_OPERATION_INPUT_CONFLICT"):
        await service.execute(
            "hr.resume.structure",
            request.model_copy(update={"candidate_ref": "other"}),
            control,
        )


@pytest.mark.asyncio
async def test_explanation_requires_existing_assessments_and_cannot_rejudge():
    from efficiency_platform_agent.contracts.hr import ExplanationOutput

    service = HrSkillService(
        FakeAssembler(ExplanationOutput), FakeProvider(['{"highlights":[],"gaps":[]}'])
    )
    with pytest.raises(ValueError, match="HR_EVALUATION_ASSESSMENTS_REQUIRED"):
        await service.execute(
            "hr.match.explain",
            HrSkillRequest(
                run_id="r",
                operation_id="o",
                requirements=[{"requirement_id": "a", "criterion": "Python"}],
            ),
            RunControl(),
        )


@pytest.mark.asyncio
async def test_fact_piece_quotes_are_mapped_to_original_block_offsets():
    import json

    from efficiency_platform_agent.contracts.hr import FactOutput
    from efficiency_platform_agent.core.execution_control import consume_http_attempt
    from efficiency_platform_agent.core.run import (
        ProviderMessage,
        ProviderResult,
        ProviderUsage,
    )

    class Provider:
        async def complete(self, request):
            consume_http_attempt()
            payload = json.loads(request.messages[1].content)
            block = payload["blocks"][0]
            quote = block["text"][:6]
            output = {
                "facts": [
                    {
                        "fact_id": block["block_id"],
                        "kind": "skill",
                        "value": quote,
                        "evidence": [
                            {
                                "block_id": block["block_id"],
                                "start": 0,
                                "end": 6,
                                "quote": quote,
                            }
                        ],
                    }
                ]
            }
            return ProviderResult(
                "provider-result/1",
                ProviderMessage("assistant", json.dumps(output)),
                ProviderUsage(1, 1, 0, 0, 0),
            )

    text = "Python" * 15000
    service = HrSkillService(FakeAssembler(FactOutput), Provider())
    result = await service.execute(
        "hr.resume.structure",
        HrSkillRequest(
            run_id="r",
            operation_id="o",
            blocks=[{"block_id": "original", "text": text}],
        ),
        RunControl(),
    )
    facts = result["data"]["facts"]
    assert len(facts) > 1
    for fact in facts:
        evidence = fact["evidence"][0]
        assert evidence["block_id"] == "original"
        assert text[evidence["start"] : evidence["end"]] == evidence["quote"]
    assert facts[-1]["evidence"][0]["start"] > 0
