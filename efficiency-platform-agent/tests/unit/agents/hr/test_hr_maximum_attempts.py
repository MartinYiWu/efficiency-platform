"""业务冻结的较低重试上限在Schema与网络实际发送共享生效。"""

import pytest

from efficiency_platform_agent.agents.hr.service import HrSkillService
from efficiency_platform_agent.contracts.hr import ExplanationOutput, HrSkillRequest
from efficiency_platform_agent.core.execution_control import RunControl
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger
from tests.unit.agents.hr.test_hr_service import FakeAssembler, FakeProvider


def test_one_attempt_limit_is_frozen_across_process_reopen(tmp_path):
    path = tmp_path / "fake-only.db"
    ledger = SqlitePaidBudgetLedger(path)
    ledger.bind_execution("t", "r", 600000, maximum_attempts=1)
    ledger.claim_execution_operation("t", "r", "op", "hash")
    ledger.consume_execution_attempt("t", "r", "op")
    reopened = SqlitePaidBudgetLedger(path)
    reopened.bind_execution("t", "r", 600000, maximum_attempts=3)
    with pytest.raises(PaidBudgetError) as error:
        reopened.consume_execution_attempt("t", "r", "op")
    assert error.value.code == "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
    with reopened._db() as db:
        assert (
            db.execute(
                "SELECT calls FROM execution_runs WHERE tenant='t' AND run='r'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.asyncio
async def test_one_attempt_schema_failure_does_not_send_a_second_provider_request():
    provider = FakeProvider(["{}"] * 3)
    request = HrSkillRequest(
        run_id="one",
        operation_id="one",
        maximum_attempts=1,
        blocks=[{"block_id": "b", "text": "Java"}],
        requirements=[{"requirement_id": "r", "criterion": "Java"}],
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
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_execution_budget_metadata_never_reaches_provider_prompt_variables():
    class RecordingProvider(FakeProvider):
        async def complete(self, request):
            self.messages = request.messages
            return await super().complete(request)

    provider = RecordingProvider(['{"highlights":[],"gaps":[]}'])
    assembler = FakeAssembler(ExplanationOutput)
    request = HrSkillRequest(
        run_id="private-run",
        operation_id="private-operation",
        maximum_attempts=1,
        workload_budget_ref="private-budget",
        workload_plan_ref="a" * 64,
        blocks=[{"block_id": "b", "text": "Java"}],
        requirements=[{"requirement_id": "r", "criterion": "Java"}],
        assessments=[
            {
                "requirement_id": "r",
                "status": "MATCH",
                "reason": "Java",
                "evidence": [{"block_id": "b", "start": 0, "end": 4, "quote": "Java"}],
            }
        ],
    )
    await HrSkillService(assembler, provider).execute(
        "hr.match.explain", request, RunControl()
    )
    supplied = assembler.inputs[0]["variables"]["input_json"].value
    assert not {
        "workload",
        "workload_budget_ref",
        "workload_plan_ref",
        "maximum_attempts",
        "expected_bindings",
        "run_id",
        "operation_id",
        "contract_version",
    }.intersection(supplied)
    prompt = " ".join(str(m.content) for m in provider.messages)
    assert (
        "private-budget" not in prompt
        and "private-operation" not in prompt
        and "private-run" not in prompt
        and "a" * 64 not in prompt
    )
    assert "Java" in prompt


@pytest.mark.asyncio
async def test_network_retry_and_schema_repair_share_frozen_single_send_limit(tmp_path):
    from efficiency_platform_agent.core.execution_control import (
        consume_http_attempt,
        execution_scope,
    )
    from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore

    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    store = PersistentHrRunControlStore(ledger)
    control = await store.get("t", "network", 1)
    sent = []

    async def work():
        with execution_scope(control):
            consume_http_attempt()
            sent.append("network-send")
            consume_http_attempt()
            sent.append("network-retry-must-not-send")

    with pytest.raises(PaidBudgetError, match="attempts exhausted"):
        await control.execute("one-operation", work)
    assert sent == ["network-send"]
    await store.close()


@pytest.mark.asyncio
async def test_cpu_only_extract_has_no_actual_attempts(tmp_path):
    import base64
    import hashlib

    from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore

    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    store = PersistentHrRunControlStore(ledger)
    control = await store.get("t", "cpu", 1)
    raw = b"synthetic CPU-only resume"
    request = HrSkillRequest(
        run_id="cpu",
        operation_id="cpu",
        maximum_attempts=1,
        extraction={
            "filename": "resume.txt",
            "content_base64": base64.b64encode(raw).decode(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    )
    await HrSkillService(None, None).execute("hr.resume.extract", request, control)
    with ledger._db() as db:
        assert (
            db.execute(
                "SELECT calls FROM execution_runs WHERE tenant='t' AND run='cpu'"
            ).fetchone()[0]
            == 0
        )
    await store.close()


@pytest.mark.asyncio
async def test_existing_run_keeps_first_attempt_default_when_later_global_default_changes(
    tmp_path,
):
    from efficiency_platform_agent.harness.hr_factory import PersistentHrRunControlStore

    ledger = SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    store = PersistentHrRunControlStore(ledger)
    original = await store.get("t", "old-three", 3)
    later = await store.get("t", "old-three", 1)
    assert original is later and later.maximum_attempts == 3
    limited = await store.get("t", "old-one", 1)
    assert limited.maximum_attempts == 1
    reopened = PersistentHrRunControlStore(
        SqlitePaidBudgetLedger(tmp_path / "fake-only.db")
    )
    assert (await reopened.get("t", "old-one", 3)).maximum_attempts == 1
    await reopened.close()
    await store.close()
