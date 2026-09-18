"""X04 服务器端真实验收授权与预算硬绑定。"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LiveAcceptanceRequestV1,
)
from efficiency_platform_agent.core.budget_execution import (
    current_budget_execution_binding,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetCharge,
    BudgetExhaustedError,
)
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.harness.live_acceptance import (
    ConversationLiveAcceptanceRunner,
    InMemoryLiveAcceptanceAuthorizationStore,
    InMemoryLiveAcceptanceBudgetBinder,
    JsonLiveAcceptanceAuthorizationStore,
    LiveAcceptanceAuthorization,
    LiveAcceptanceError,
    LiveAcceptanceService,
    PostgresLiveAcceptanceBudgetBinder,
)
from efficiency_platform_agent.persistence.research_budget import (
    PostgresBudgetLeaseRepository,
)

NOW = datetime(2026, 9, 17, 8, tzinfo=UTC)


class _BudgetedRunner:
    def __init__(self, cost_per_case: int = 30) -> None:
        self.cost_per_case = cost_per_case
        self.calls: list[str] = []

    async def run_case(self, case_id, prompt, binding):
        self.calls.append(case_id)
        reservation = await binding.port.reserve(
            binding.scope,
            f"case:{case_id}",
            BudgetCharge(calls=1, cost_microunits=self.cost_per_case),
            (await binding.port.snapshot(binding.scope)).version,
        )
        await binding.port.mark_dispatched(reservation.reservation_id)
        await binding.port.settle(
            reservation.reservation_id,
            BudgetCharge(calls=1, cost_microunits=self.cost_per_case),
            "success",
        )
        return {
            "case_id": case_id,
            "status": "PASS",
            "run_id": f"run-{case_id}",
            "real_model_verified": True,
            "real_source_verified": case_id != "ordinary_chat",
        }


def _authorization(*, budget: int = 100) -> LiveAcceptanceAuthorization:
    return LiveAcceptanceAuthorization(
        authorization_id="approval-1",
        approved_by="project-owner",
        approved_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        allowed_actions=frozenset({"model_evaluation", "source_read"}),
        allowed_case_ids=("yesterday_ai", "ordinary_chat"),
        allowed_tenant_ids=("tenant-acceptance",),
        max_budget_microunits=budget,
    )


def _request(*, budget: int = 100, request_id: str = "acceptance-1"):
    return LiveAcceptanceRequestV1(
        request_id=request_id,
        authorization_id="approval-1",
        case_ids=("yesterday_ai", "ordinary_chat"),
        requested_budget_microunits=budget,
    )


@pytest.mark.asyncio
async def test_server_authorization_binds_budget_and_is_idempotent() -> None:
    runner = _BudgetedRunner()
    binder = InMemoryLiveAcceptanceBudgetBinder(clock_ms=lambda: 1_789_632_000_000)
    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((_authorization(),)),
        budget_binder=binder,
        runner=runner,
        now=lambda: NOW,
    )

    first = await service.execute(_request(), tenant_id="tenant-acceptance")
    replay = await service.execute(_request(), tenant_id="tenant-acceptance")

    assert first == replay
    assert first.status == "PASS"
    assert first.external_io is True
    assert first.used_cost_microunits == 60
    assert first.approved_budget_microunits == 100
    assert runner.calls == ["yesterday_ai", "ordinary_chat"]
    assert binder.binding_count == 1


@pytest.mark.asyncio
async def test_server_budget_stops_second_case_before_overspend() -> None:
    runner = _BudgetedRunner(cost_per_case=30)
    binder = InMemoryLiveAcceptanceBudgetBinder(clock_ms=lambda: 1_789_632_000_000)
    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore(
            (_authorization(budget=50),)
        ),
        budget_binder=binder,
        runner=runner,
        now=lambda: NOW,
    )

    result = await service.execute(
        _request(budget=50), tenant_id="tenant-acceptance"
    )

    assert result.status == "FAILED"
    assert result.reason_codes == ("LIVE_BUDGET_EXHAUSTED",)
    assert result.used_cost_microunits == 30
    assert runner.calls == ["yesterday_ai", "ordinary_chat"]
    binding = binder.binding_for("tenant-acceptance", "approval-1")
    snapshot = await binding.port.snapshot(binding.scope)
    assert snapshot.used.cost_microunits == 30
    assert snapshot.reserved.cost_microunits == 0
    with pytest.raises(BudgetExhaustedError):
        await binding.port.reserve(
            binding.scope,
            "after-terminal",
            BudgetCharge(calls=1),
            snapshot.version,
        )


@pytest.mark.asyncio
async def test_server_preserves_case_result_mismatch_reason_code() -> None:
    class MismatchedRunner:
        async def run_case(self, case_id, prompt, binding):
            return {
                "case_id": "ordinary_chat",
                "status": "PASS",
                "run_id": "run-mismatched",
                "real_model_verified": True,
                "real_source_verified": True,
            }

    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((_authorization(),)),
        budget_binder=InMemoryLiveAcceptanceBudgetBinder(),
        runner=MismatchedRunner(),
        now=lambda: NOW,
    )

    result = await service.execute(_request(), tenant_id="tenant-acceptance")

    assert result.status == "FAILED"
    assert result.reason_codes == ("LIVE_CASE_RESULT_MISMATCH",)


@pytest.mark.asyncio
async def test_server_rejects_unapproved_tenant_before_binding_or_runner() -> None:
    runner = _BudgetedRunner()
    binder = InMemoryLiveAcceptanceBudgetBinder()
    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((_authorization(),)),
        budget_binder=binder,
        runner=runner,
        now=lambda: NOW,
    )

    with pytest.raises(LiveAcceptanceError, match="LIVE_TENANT_NOT_AUTHORIZED"):
        await service.execute(_request(), tenant_id="tenant-other")

    assert runner.calls == []
    assert binder.binding_count == 0


@pytest.mark.asyncio
async def test_same_request_id_cannot_change_budget_or_cases() -> None:
    runner = _BudgetedRunner()
    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((_authorization(),)),
        budget_binder=InMemoryLiveAcceptanceBudgetBinder(
            clock_ms=lambda: int(NOW.timestamp() * 1_000)
        ),
        runner=runner,
        now=lambda: NOW,
    )
    await service.execute(_request(), tenant_id="tenant-acceptance")

    with pytest.raises(LiveAcceptanceError, match="LIVE_REQUEST_ID_CONFLICT"):
        await service.execute(
            LiveAcceptanceRequestV1(
                request_id="acceptance-1",
                authorization_id="approval-1",
                case_ids=("ordinary_chat",),
                requested_budget_microunits=100,
            ),
            tenant_id="tenant-acceptance",
        )


@pytest.mark.asyncio
async def test_authorization_cannot_be_reused_with_a_new_request_id() -> None:
    runner = _BudgetedRunner()
    service = LiveAcceptanceService(
        authorizations=InMemoryLiveAcceptanceAuthorizationStore((_authorization(),)),
        budget_binder=InMemoryLiveAcceptanceBudgetBinder(
            clock_ms=lambda: int(NOW.timestamp() * 1_000)
        ),
        runner=runner,
        now=lambda: NOW,
    )
    await service.execute(_request(), tenant_id="tenant-acceptance")

    with pytest.raises(LiveAcceptanceError, match="LIVE_AUTHORIZATION_REUSED"):
        await service.execute(
            _request(request_id="acceptance-2"),
            tenant_id="tenant-acceptance",
        )

    assert runner.calls == ["yesterday_ai", "ordinary_chat"]


def test_server_loads_authorization_from_trusted_local_file(tmp_path: Path) -> None:
    path = tmp_path / "approval.json"
    path.write_text(
        json.dumps(
            {
                "version": "x04-live-authorization/1",
                "authorization_id": "approval-file-1",
                "approved_by": "project-owner",
                "approved_at": (NOW - timedelta(minutes=1)).isoformat(),
                "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
                "allowed_actions": ["model_evaluation", "source_read"],
                "allowed_case_ids": ["ordinary_chat"],
                "allowed_tenant_ids": ["tenant-acceptance"],
                "max_budget_microunits": 200,
            }
        ),
        encoding="utf-8",
    )

    store = JsonLiveAcceptanceAuthorizationStore.from_files((path,))

    record = store.get("approval-file-1")
    assert record is not None
    assert record.allowed_tenant_ids == ("tenant-acceptance",)
    assert record.max_budget_microunits == 200


def test_postgres_binder_builds_authoritative_budget_port_and_rejects_reuse() -> None:
    binder = PostgresLiveAcceptanceBudgetBinder(object(), "agent_runtime")

    first = binder.bind(
        _authorization(), _request(), tenant_id="tenant-acceptance"
    )
    replay = binder.bind(
        _authorization(), _request(), tenant_id="tenant-acceptance"
    )

    assert replay is first
    assert isinstance(first.port, PostgresBudgetLeaseRepository)
    assert first.scope.tenant_id == "tenant-acceptance"
    assert first.port.default_limits.max_cost_microunits == 100
    with pytest.raises(LiveAcceptanceError, match="LIVE_AUTHORIZATION_REUSED"):
        binder.bind(
            _authorization(),
            _request(request_id="different-request"),
            tenant_id="tenant-acceptance",
        )


@pytest.mark.asyncio
async def test_conversation_runner_propagates_binding_into_background_task() -> None:
    captured = []

    class Conversation:
        async def submit(self, conversation_id, tenant_id, message):
            assert conversation_id.startswith("live-acceptance-")
            assert tenant_id == "tenant-acceptance"

            async def background():
                await asyncio.sleep(0)
                captured.append(current_budget_execution_binding())

            task = asyncio.create_task(background())
            runtime.task = task
            return SimpleNamespace(run_id="run-live-1")

    class Runtime:
        task = None

        async def wait_for_background_tasks(self):
            await self.task

        async def get_run(self, run_id, tenant_id):
            return SimpleNamespace(
                run_id=run_id,
                status=RunStatus.SUCCEEDED,
                usage=SimpleNamespace(
                    estimated=False,
                    input_tokens=10,
                    output_tokens=20,
                ),
                output={
                    "deliverables": [
                        {"citations": [{"url": "https://official.example/news"}]}
                    ]
                },
                degraded=False,
            )

    runtime = Runtime()
    binder = InMemoryLiveAcceptanceBudgetBinder(
        clock_ms=lambda: int(NOW.timestamp() * 1_000)
    )
    binding = binder.bind(
        _authorization(), _request(), tenant_id="tenant-acceptance"
    )
    runner = ConversationLiveAcceptanceRunner(Conversation(), runtime)

    result = await runner.run_case(
        "yesterday_ai",
        "收集昨天的 AI 行业动态并输出带来源摘要。",
        binding,
    )

    assert captured == [binding]
    assert result.status == "PASS"
    assert result.real_model_verified is True
    assert result.real_source_verified is True
