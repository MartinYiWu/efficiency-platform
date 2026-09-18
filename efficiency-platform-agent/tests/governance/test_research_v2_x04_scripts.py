"""X04 真实准入工具链的离线安全门禁。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from efficiency_platform_agent.evaluation.intent_v2 import load_intent_dataset
from efficiency_platform_agent.providers.research.admission_probe import (
    LiveSourceProbeError,
)
from scripts.intent_v2_evaluate import evaluate_replay
from scripts.research_v2_acceptance import (
    LIVE_CASES,
    evaluate_offline_case,
    execute_live_acceptance,
    validate_live_authorization,
)
from scripts.research_v2_preflight import build_preflight, create_live_probe

ROOT = Path(__file__).parents[2]


def test_preflight_default_is_plan_only_and_never_calls_probe() -> None:
    calls: list[str] = []

    def forbidden_probe(_url: str) -> dict[str, object]:
        calls.append("called")
        raise AssertionError("默认预检不得发起网络请求")

    result = build_preflight(
        source_config=ROOT / "config/research_sources.toml",
        admission_records=ROOT
        / "docs/superpowers/sdd/intent-research-v2/来源准入候选记录.json",
        execute=False,
        probe=forbidden_probe,
    )

    assert result["status"] == "PLAN_ONLY"
    assert result["external_io"] is False
    assert result["probed_source_count"] == 0
    assert result["eligible_source_count"] == 3
    assert calls == []


def test_preflight_execute_fails_closed_before_probe_for_unverified_sources() -> None:
    calls: list[str] = []

    result = build_preflight(
        source_config=ROOT / "config/research_sources.toml",
        admission_records=ROOT
        / "docs/superpowers/sdd/intent-research-v2/来源准入候选记录.json",
        execute=True,
        authorization_file=None,
        probe=lambda url: calls.append(url) or {"status_code": 200},
    )

    assert result["status"] == "BLOCKED"
    assert "AUTHORIZATION_REQUIRED" in result["reason_codes"]
    assert result["reason_codes"] == ["AUTHORIZATION_REQUIRED"]
    assert result["external_io"] is False
    assert calls == []


def test_admission_record_separates_live_verified_and_unprobed_sources() -> None:
    record_path = (
        ROOT / "docs/superpowers/sdd/intent-research-v2/来源准入候选记录.json"
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))

    assert payload["version"] == "x04-source-admission-candidates/1"
    assert len(payload["records"]) == 5
    by_id = {record["source_id"]: record for record in payload["records"]}
    for source_id in (
        "fixture_official_feed",
        "fixture_github_releases",
        "fixture_hacker_news",
    ):
        assert by_id[source_id]["status"] == "VERIFIED"
        assert by_id[source_id]["checked_at"]
    for source_id in ("fixture_arxiv", "fixture_gdelt"):
        assert by_id[source_id]["status"] == "UNVERIFIED"
        assert by_id[source_id]["checked_at"] == ""
    for record in payload["records"]:
        assert record["cost_evidence_url"].startswith("https://")
        assert record["permission_evidence_url"].startswith("https://")
        assert record["schema"] != "unknown"
        assert record["rate_limit"] != ""
        assert record["history_range"] != ""
        assert record["allowed_storage"] != ""

    result = build_preflight(
        source_config=ROOT / "config/research_sources.toml",
        admission_records=record_path,
        execute=False,
    )

    assert result["eligible_source_count"] == 3
    result_by_id = {source["source_id"]: source for source in result["sources"]}
    assert all(
        result_by_id[source_id]["eligible"]
        for source_id in (
            "fixture_official_feed",
            "fixture_github_releases",
            "fixture_hacker_news",
        )
    )
    assert all(
        not result_by_id[source_id]["eligible"]
        and "SOURCE_CONFIG_UNVERIFIED" in result_by_id[source_id]["reason_codes"]
        for source_id in ("fixture_arxiv", "fixture_gdelt")
    )


def test_preflight_calls_injected_probe_only_after_all_gates(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 8, tzinfo=UTC)
    config = tmp_path / "sources.toml"
    config.write_text(
        """config_version = "test/1"
[[sources]]
source_id = "source-free"
adapter_id = "rss_atom"
enabled = true
cost_mode = "free"
admission_status = "VERIFIED"
""",
        encoding="utf-8",
    )
    records = tmp_path / "records.json"
    records.write_text(
        json.dumps(
            {
                "version": "x04-source-admission-candidates/1",
                "records": [
                    {
                        "source_id": "source-free",
                        "status": "VERIFIED",
                        "endpoint_url": "https://feed.example/rss",
                        "schema": "RSS 2.0",
                        "checked_at": now.isoformat(),
                        "cost_evidence_url": "https://feed.example/cost",
                        "permission_evidence_url": "https://feed.example/terms",
                        "rate_limit": "10/minute",
                        "history_range": "latest 30 days",
                        "allowed_storage": "metadata and excerpt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "version": "x04-source-read-authorization/1",
                "authorization_id": "source-approval-1",
                "approved_by": "project-owner",
                "approved_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "allowed_actions": ["source_read"],
                "allowed_source_ids": ["source-free"],
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    result = build_preflight(
        source_config=config,
        admission_records=records,
        execute=True,
        authorization_file=approval,
        probe=lambda url: (
            calls.append(url) or {"status_code": 200, "schema_valid": True}
        ),
        now=now,
    )

    assert result["status"] == "PASS"
    assert result["execution_status"] == "EXECUTED"
    assert result["external_io"] is True
    assert result["probed_source_count"] == 1
    assert calls == ["https://feed.example/rss"]

    bound_probe = create_live_probe(
        source_config=config,
        admission_records=records,
        authorization_file=approval,
        now=now,
    )
    with pytest.raises(LiveSourceProbeError, match="LIVE_PROBE_TARGET_NOT_REGISTERED"):
        bound_probe("https://other.example/rss")


def test_preflight_execute_fails_closed_when_source_probe_is_not_bound(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 17, 8, tzinfo=UTC)
    config = tmp_path / "sources.toml"
    config.write_text(
        """config_version = "test/1"
[[sources]]
source_id = "source-free"
adapter_id = "rss_atom"
enabled = true
cost_mode = "free"
admission_status = "VERIFIED"
""",
        encoding="utf-8",
    )
    records = tmp_path / "records.json"
    records.write_text(
        json.dumps(
            {
                "version": "x04-source-admission-candidates/1",
                "records": [
                    {
                        "source_id": "source-free",
                        "status": "VERIFIED",
                        "endpoint_url": "https://feed.example/rss",
                        "schema": "RSS 2.0",
                        "checked_at": now.isoformat(),
                        "cost_evidence_url": "https://feed.example/cost",
                        "permission_evidence_url": "https://feed.example/terms",
                        "rate_limit": "10/minute",
                        "history_range": "latest 30 days",
                        "allowed_storage": "metadata and excerpt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "version": "x04-source-read-authorization/1",
                "authorization_id": "source-approval-1",
                "approved_by": "project-owner",
                "approved_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
                "allowed_actions": ["source_read"],
                "allowed_source_ids": ["source-free"],
            }
        ),
        encoding="utf-8",
    )

    result = build_preflight(
        source_config=config,
        admission_records=records,
        execute=True,
        authorization_file=approval,
        probe=None,
        now=now,
    )

    assert result["status"] == "BLOCKED"
    assert result["external_io"] is False
    assert result["reason_codes"] == ["LIVE_SOURCE_PROBE_NOT_BOUND"]


def test_offline_acceptance_uses_recorded_evidence_without_claiming_real() -> None:
    result = evaluate_offline_case(
        "yesterday_ai",
        ROOT / "docs/superpowers/sdd/intent-research-v2/task-X03-offline-evidence.json",
    )

    assert result["status"] == "PASS"
    assert result["execution_mode"] == "offline_replay"
    assert result["external_io"] is False
    assert result["real_source_verified"] is False
    assert result["real_model_verified"] is False
    assert result["outcome"] == "PARTIAL"


def test_live_matrix_freezes_the_five_required_case_types() -> None:
    assert tuple(LIVE_CASES) == (
        "yesterday_ai",
        "last_week_topic",
        "exact_five",
        "rewrite_wechat",
        "ordinary_chat",
    )


def test_live_authorization_requires_positive_budget_and_unexpired_record(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 17, 8, tzinfo=UTC)
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "version": "x04-live-authorization/1",
                "authorization_id": "approval-1",
                "approved_by": "project-owner",
                "approved_at": (now - timedelta(minutes=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=30)).isoformat(),
                "allowed_actions": ["model_evaluation", "source_read"],
                "allowed_case_ids": list(LIVE_CASES),
                "allowed_tenant_ids": ["tenant-acceptance"],
                "max_budget_microunits": 500,
            }
        ),
        encoding="utf-8",
    )

    accepted = validate_live_authorization(
        approval,
        requested_budget_microunits=500,
        requested_actions=("model_evaluation",),
        requested_case_ids=("ordinary_chat",),
        requested_tenant_id="tenant-acceptance",
        now=now,
    )
    assert accepted["authorization_id"] == "approval-1"

    with pytest.raises(ValueError, match="LIVE_BUDGET_REQUIRED"):
        validate_live_authorization(
            approval,
            requested_budget_microunits=0,
            requested_actions=("model_evaluation",),
            requested_case_ids=("ordinary_chat",),
            requested_tenant_id="tenant-acceptance",
            now=now,
        )


def test_live_client_posts_only_frozen_ids_to_loopback_server() -> None:
    calls: list[tuple[str, dict[str, object], dict[str, str], float]] = []

    def requester(url, payload, headers, timeout):
        calls.append((url, payload, headers, timeout))
        return {
            "contract_version": "research-live-acceptance/1",
            "request_id": "live-request-1",
            "authorization_id": "approval-1",
            "acceptance_session_id": "live-acceptance-session",
            "status": "PASS",
            "execution_mode": "live",
            "external_io": True,
            "approved_budget_microunits": 500,
            "used_cost_microunits": 120,
            "case_results": [
                {
                    "case_id": "ordinary_chat",
                    "status": "PASS",
                    "run_id": "run-ordinary-chat",
                    "real_model_verified": True,
                    "real_source_verified": False,
                }
            ],
            "reason_codes": [],
        }

    result = execute_live_acceptance(
        base_url="http://127.0.0.1:8000",
        tenant_id="tenant-acceptance",
        request_id="live-request-1",
        authorization_id="approval-1",
        case_ids=("ordinary_chat",),
        approved_budget_microunits=500,
        timeout_seconds=30.0,
        requester=requester,
    )

    assert result["status"] == "PASS"
    assert calls == [
        (
            "http://127.0.0.1:8000/v1/internal/research-v2/live-acceptance",
            {
                "contract_version": "research-live-acceptance/1",
                "request_id": "live-request-1",
                "authorization_id": "approval-1",
                "case_ids": ["ordinary_chat"],
                "requested_budget_microunits": 500,
            },
            {"X-Tenant-ID": "tenant-acceptance"},
            30.0,
        )
    ]


def test_live_client_rejects_non_loopback_base_url_before_request() -> None:
    with pytest.raises(ValueError, match="LIVE_BASE_URL_NOT_LOOPBACK"):
        execute_live_acceptance(
            base_url="https://agent.example.com",
            tenant_id="tenant-acceptance",
            request_id="live-request-1",
            authorization_id="approval-1",
            case_ids=("ordinary_chat",),
            approved_budget_microunits=500,
            timeout_seconds=30.0,
            requester=lambda *_: pytest.fail("非本机地址不得请求"),
        )


def test_replay_without_predictions_reports_dataset_ready_not_fake_metrics() -> None:
    report = evaluate_replay(
        dataset_root=ROOT / "tests/fixtures/intent_v2",
        split="frozen",
        prediction_files=(),
    )

    assert report["status"] == "NOT_EXECUTED"
    assert report["reason_codes"] == ["PREDICTIONS_REQUIRED"]
    assert report["dataset_count"] == 60
    assert report["evaluation_run_count"] == 0
    assert "metrics" not in report


def test_replay_requires_three_independent_prediction_runs(tmp_path: Path) -> None:
    prediction = tmp_path / "run-1.json"
    prediction.write_text(
        json.dumps(
            {
                "schema_version": "intent-evaluation-predictions/2",
                "run_id": "run-1",
                "dataset_version": "2026-09-16.1",
                "split": "frozen",
                "model_id": "recorded-model",
                "prompt_versions": ["intent-interpret-v2"],
                "usage": {
                    "model_calls": 60,
                    "failed_model_calls": 0,
                    "cost_microunits": 1,
                },
                "predictions": [],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_replay(
        dataset_root=ROOT / "tests/fixtures/intent_v2",
        split="frozen",
        prediction_files=(prediction,),
    )

    assert report["status"] == "NOT_EXECUTED"
    assert report["reason_codes"] == ["THREE_INDEPENDENT_RUNS_REQUIRED"]
    assert report["evaluation_run_count"] == 1


def test_replay_scores_three_fixed_runs_without_prediction_order_coupling(
    tmp_path: Path,
) -> None:
    dataset_root = ROOT / "tests/fixtures/intent_v2"
    manifest, all_cases = load_intent_dataset(dataset_root)
    cases = [case for case in all_cases if case.case_id.startswith("frozen-")]
    predictions = [
        {
            "case_id": case.case_id,
            "fields": case.expected_fields,
            "decision": case.expected_decision,
            "capabilities": list(case.expected_capabilities),
        }
        for case in cases
    ]
    paths: list[Path] = []
    for index in range(3):
        path = tmp_path / f"run-{index}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "intent-evaluation-predictions/2",
                    "run_id": f"run-{index}",
                    "dataset_version": manifest.dataset_version,
                    "split": "frozen",
                    "model_id": "fixed-model",
                    "prompt_versions": ["intent-interpret-v2"],
                    "usage": {
                        "model_calls": 60,
                        "failed_model_calls": 0,
                        "cost_microunits": 10,
                    },
                    "predictions": list(reversed(predictions))
                    if index == 2
                    else predictions,
                }
            ),
            encoding="utf-8",
        )
        paths.append(path)

    report = evaluate_replay(
        dataset_root=dataset_root,
        split="frozen",
        prediction_files=tuple(paths),
    )

    assert report["status"] == "PASS"
    assert report["evaluation_run_count"] == 3
    assert report["usage"] == {
        "model_calls": 180,
        "failed_model_calls": 0,
        "cost_microunits": 30,
    }
    assert all(run["metrics"]["ready_precision"] == 1.0 for run in report["runs"])
