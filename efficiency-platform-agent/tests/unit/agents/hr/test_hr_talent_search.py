import pytest

from efficiency_platform_agent.contracts.hr import Block, HrSkillRequest


def test_talent_search_requires_exact_source_quotes_and_bounded_relevance():
    from efficiency_platform_agent.agents.hr.talent import validate_search
    from efficiency_platform_agent.contracts.hr import TalentSearchOutput

    request = HrSkillRequest(
        run_id="r",
        operation_id="o",
        search_query="Java",
        blocks=[Block(block_id="b", text="负责Java订单服务")],
    )
    valid = TalentSearchOutput.model_validate(
        {
            "relevance": 0.8,
            "matches": [{"block_id": "b", "start": 2, "end": 6, "quote": "Java"}],
        }
    )
    validate_search(valid, request)
    with pytest.raises(ValueError):
        validate_search(
            TalentSearchOutput.model_validate(
                {
                    "relevance": 0.9,
                    "matches": [
                        {"block_id": "b", "start": 0, "end": 4, "quote": "Java"}
                    ],
                }
            ),
            request,
        )
    with pytest.raises(ValueError):
        TalentSearchOutput.model_validate({"relevance": 1.1, "matches": []})


def test_search_skill_has_dedicated_published_binding_and_workload():
    from efficiency_platform_agent.agents.hr.definition import SKILLS
    from efficiency_platform_agent.contracts.hr import HrWorkload

    assert SKILLS[6110] == "hr.talent.search"
    assert (
        HrWorkload(run_ref="hr-search-abc", skill_key="hr.talent.search").attempts == 3
    )


@pytest.mark.asyncio
async def test_search_model_uses_only_query_blocks_and_replays_without_new_attempt():
    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.contracts.hr import TalentSearchOutput
    from efficiency_platform_agent.core.execution_control import RunControl
    from tests.unit.agents.hr.test_hr_service import FakeAssembler, FakeProvider

    assembler = FakeAssembler(TalentSearchOutput)
    provider = FakeProvider(
        [
            '{"relevance":0.8,"matches":[{"block_id":"b","start":2,"end":6,"quote":"Java"}]}'
        ]
    )
    service = HrSkillService(assembler, provider)
    request = HrSkillRequest(
        run_id="r",
        operation_id="o",
        search_query="Java",
        candidate_ref="hidden-ref",
        workload_budget_ref="secret-budget",
        blocks=[Block(block_id="b", text="负责Java订单服务")],
    )
    control = RunControl()
    first = await service.execute("hr.talent.search", request, control)
    assert first["data"]["relevance"] == 0.8
    assert set(assembler.inputs[0]["variables"]["input_json"].value) == {
        "search_query",
        "blocks",
    }
    assert await service.execute("hr.talent.search", request, control) == first
    assert provider.calls == 1
