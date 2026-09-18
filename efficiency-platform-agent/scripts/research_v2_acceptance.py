"""X04 研究闭环验收入口；默认只回放脱敏离线证据。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import selectors
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlsplit

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
for search_path in (PROJECT_ROOT, SOURCE_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from efficiency_platform_agent.contracts.live_acceptance_v2 import (  # type: ignore[import-untyped]
    LIVE_ACCEPTANCE_CASE_PROMPTS,
    LiveAcceptanceRequestV1,
    LiveAcceptanceViewV1,
)

LIVE_CASES: dict[str, str] = dict(LIVE_ACCEPTANCE_CASE_PROMPTS)

type LiveRequester = Callable[
    [str, dict[str, object], dict[str, str], float], Mapping[str, object]
]


def _run_async(coroutine):
    if sys.platform == "win32":
        return asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            ),
        )
    return asyncio.run(coroutine)


class LiveAcceptanceClientError(ValueError):
    def __init__(self, reason_code: str, *, request_attempted: bool) -> None:
        self.reason_code = reason_code
        self.request_attempted = request_attempted
        super().__init__(reason_code)


class ValidatedLiveAuthorization(TypedDict):
    authorization_id: str
    approved_budget_microunits: int


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_live_authorization(
    path: Path,
    *,
    requested_budget_microunits: int,
    requested_actions: tuple[str, ...],
    requested_case_ids: tuple[str, ...],
    requested_tenant_id: str,
    now: datetime | None = None,
) -> ValidatedLiveAuthorization:
    """校验既有真实验收授权；不读取环境密钥，也不创建账户。"""

    if requested_budget_microunits <= 0:
        raise ValueError("LIVE_BUDGET_REQUIRED")
    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("LIVE_AUTHORIZATION_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("LIVE_AUTHORIZATION_INVALID") from exc
    if not isinstance(payload, dict):
        raise TypeError("LIVE_AUTHORIZATION_INVALID")
    approved_at = _parse_time(payload.get("approved_at"))
    expires_at = _parse_time(payload.get("expires_at"))
    allowed_actions = payload.get("allowed_actions")
    allowed_cases = payload.get("allowed_case_ids")
    allowed_tenants = payload.get("allowed_tenant_ids")
    approved_budget = payload.get("max_budget_microunits")
    if not (
        payload.get("version") == "x04-live-authorization/1"
        and isinstance(payload.get("authorization_id"), str)
        and payload["authorization_id"].strip()
        and isinstance(payload.get("approved_by"), str)
        and payload["approved_by"].strip()
        and approved_at is not None
        and expires_at is not None
        and approved_at <= observed_at < expires_at
        and isinstance(allowed_actions, list)
        and all(isinstance(item, str) for item in allowed_actions)
        and set(requested_actions).issubset(set(allowed_actions))
        and isinstance(allowed_cases, list)
        and all(isinstance(item, str) for item in allowed_cases)
        and set(requested_case_ids).issubset(set(allowed_cases))
        and isinstance(allowed_tenants, list)
        and all(isinstance(item, str) and item.strip() for item in allowed_tenants)
        and requested_tenant_id in allowed_tenants
        and isinstance(approved_budget, int)
        and not isinstance(approved_budget, bool)
        and 0 < requested_budget_microunits <= approved_budget
    ):
        raise ValueError("LIVE_AUTHORIZATION_INVALID")
    return {
        "authorization_id": payload["authorization_id"],
        "approved_budget_microunits": requested_budget_microunits,
    }


def execute_live_acceptance(
    *,
    base_url: str,
    tenant_id: str,
    request_id: str,
    authorization_id: str,
    case_ids: tuple[str, ...],
    approved_budget_microunits: int,
    timeout_seconds: float,
    requester: LiveRequester | None = None,
) -> dict[str, object]:
    """只向本机 Agent 的专用入口发送冻结标识，不发送授权文件内容。"""

    try:
        parsed = urlsplit(base_url)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise LiveAcceptanceClientError(
            "LIVE_BASE_URL_INVALID", request_attempted=False
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is None
    ):
        raise LiveAcceptanceClientError(
            "LIVE_BASE_URL_NOT_LOOPBACK", request_attempted=False
        )
    if (
        not math.isfinite(timeout_seconds)
        or timeout_seconds < 1
        or timeout_seconds > 600
    ):
        raise LiveAcceptanceClientError(
            "LIVE_TIMEOUT_INVALID", request_attempted=False
        )
    request = LiveAcceptanceRequestV1(
        request_id=request_id,
        authorization_id=authorization_id,
        case_ids=case_ids,
        requested_budget_microunits=approved_budget_microunits,
    )
    endpoint = (
        base_url.rstrip("/") + "/v1/internal/research-v2/live-acceptance"
    )
    payload = request.model_dump(mode="json")
    post = requester or _post_live_acceptance
    try:
        raw_response = post(
            endpoint,
            payload,
            {"X-Tenant-ID": tenant_id},
            timeout_seconds,
        )
        view = LiveAcceptanceViewV1.model_validate(raw_response)
    except LiveAcceptanceClientError:
        raise
    except Exception as exc:
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_RESPONSE_INVALID", request_attempted=True
        ) from exc
    returned_cases = tuple(item.case_id for item in view.case_results)
    if (
        view.request_id != request_id
        or view.authorization_id != authorization_id
        or view.approved_budget_microunits != approved_budget_microunits
        or view.used_cost_microunits > approved_budget_microunits
        or returned_cases != case_ids
    ):
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_RESPONSE_MISMATCH", request_attempted=True
        )
    return view.model_dump(mode="json")


def _post_live_acceptance(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: float,
) -> Mapping[str, object]:
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_UNAVAILABLE", request_attempted=True
        ) from exc
    if response.status_code != 200:
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_REJECTED", request_attempted=True
        )
    try:
        decoded = response.json()
    except ValueError as exc:
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_RESPONSE_INVALID", request_attempted=True
        ) from exc
    if not isinstance(decoded, dict):
        raise LiveAcceptanceClientError(
            "LIVE_SERVER_RESPONSE_INVALID", request_attempted=True
        )
    return decoded


def evaluate_offline_case(case_id: str, evidence_path: Path) -> dict[str, Any]:
    """回放 X03 脱敏证据；明确区分 Fake 闭环与真实验收。"""

    if case_id not in LIVE_CASES:
        raise ValueError("ACCEPTANCE_CASE_UNKNOWN")
    if case_id != "yesterday_ai":
        return {
            "schema_version": "research-v2-acceptance/1",
            "case_id": case_id,
            "status": "NOT_EXECUTED",
            "reason_codes": ["OFFLINE_EVIDENCE_NOT_RECORDED"],
            "execution_mode": "offline_replay",
            "external_io": False,
            "real_source_verified": False,
            "real_model_verified": False,
        }
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("OFFLINE_EVIDENCE_INVALID") from exc
    claims = evidence.get("claims") if isinstance(evidence, dict) else None
    valid = bool(
        evidence.get("evidence_version") == "x03-offline-evidence/1"
        and evidence.get("network_mode") == "offline_fake_only"
        and evidence.get("resolved_window", {}).get("label") == "昨天"
        and evidence.get("citation_coverage") == 1.0
        and evidence.get("outcome") in {"COMPLETE", "PARTIAL"}
        and isinstance(claims, dict)
        and claims.get("real_source_verified") is False
        and claims.get("real_model_verified") is False
    )
    if not valid:
        raise ValueError("OFFLINE_EVIDENCE_INVALID")
    return {
        "schema_version": "research-v2-acceptance/1",
        "case_id": case_id,
        "status": "PASS",
        "execution_mode": "offline_replay",
        "external_io": False,
        "real_source_verified": False,
        "real_model_verified": False,
        "production_ready": False,
        "outcome": evidence["outcome"],
        "stop_reason": evidence["stop_reason"],
        "requested_count": evidence["requested_count"],
        "delivered_event_count": evidence["delivered_event_count"],
        "citation_coverage": evidence["citation_coverage"],
        "resolved_window": evidence["resolved_window"],
    }


async def execute_direct_local_acceptance(
    *,
    authorization_file: Path,
    tenant_id: str,
    request_id: str,
    case_ids: tuple[str, ...],
    approved_budget_microunits: int,
    database_url: str,
    env_file: Path,
) -> dict[str, object]:
    """在本机组合真实模型、免费来源和 X01 PostgreSQL 账本。"""

    from types import SimpleNamespace

    from openai import AsyncOpenAI
    from psycopg import AsyncConnection

    from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
    from efficiency_platform_agent.configuration.integration import (
        S7IntegrationSettings,
    )
    from efficiency_platform_agent.contracts.live_acceptance_v2 import (
        LiveAcceptanceRequestV1,
    )
    from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
    from efficiency_platform_agent.harness.live_acceptance import (
        JsonLiveAcceptanceAuthorizationStore,
        LiveAcceptanceService,
        PostgresLiveAcceptanceBudgetBinder,
    )
    from efficiency_platform_agent.harness.live_research_v2 import (
        FreeSourceLiveAcceptanceRunner,
        LiveFreeSourceCollector,
    )
    from efficiency_platform_agent.providers.llm.deepseek import (
        DeepSeekModelProvider,
    )
    from efficiency_platform_agent.providers.llm.registry import (
        ModelProviderRegistry,
    )
    from efficiency_platform_agent.routing.model_router import ModelPolicyRouter

    settings = S7IntegrationSettings.from_env_file(env_file)

    def required(name: str) -> str:
        value = getattr(settings, name)
        if value is None or not value.get_secret_value().strip():
            raise ValueError(f"LIVE_MODEL_CONFIGURATION_MISSING:{name}")
        return value.get_secret_value()

    api_key = required("deepseek_api_key")
    base_url = required("deepseek_base_url")
    model_id = required("deepseek_balanced_model")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=120.0,
        max_retries=0,
    )
    provider = DeepSeekModelProvider(
        SimpleNamespace(chat=client.chat, close=client.close),
        model_id,
        timeout_ms=120_000,
    )
    registry = ModelProviderRegistry()
    provider_id = "deepseek_live_research_acceptance"
    registry.register(provider_id, provider)
    candidate = ModelCandidate(
        "deepseek-live-research-acceptance",
        provider_id,
        model_id,
        ModelTier.BALANCED,
        True,
        False,
        64_000,
        True,
        False,
    )
    runner = FreeSourceLiveAcceptanceRunner(
        LiveFreeSourceCollector(),
        ModelRuntime(ModelPolicyRouter((candidate,)), registry),
    )
    connection = await AsyncConnection.connect(database_url)
    try:
        service = LiveAcceptanceService(
            authorizations=JsonLiveAcceptanceAuthorizationStore.from_files(
                (authorization_file,)
            ),
            budget_binder=PostgresLiveAcceptanceBudgetBinder(
                connection, "agent_runtime"
            ),
            runner=runner,
        )
        authorization = json.loads(authorization_file.read_text(encoding="utf-8"))
        view = await service.execute(
            LiveAcceptanceRequestV1(
                request_id=request_id,
                authorization_id=str(authorization["authorization_id"]),
                case_ids=case_ids,
                requested_budget_microunits=approved_budget_microunits,
            ),
            tenant_id=tenant_id,
        )
        return {
            **view.model_dump(mode="json"),
            "schema_version": "research-v2-live-acceptance-report/2",
            "model_id": model_id,
            "cost_observed": view.used_cost_microunits > 0,
            "source_policy": "verified-free-public-only",
            "case_evidence": runner.records,
        }
    finally:
        await connection.close()
        await provider.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--direct-local", action="store_true")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--base-url")
    parser.add_argument("--tenant-id")
    parser.add_argument("--request-id")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--approved-budget-microunits", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--database-url")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    selected = tuple(args.cases or ("yesterday_ai",))
    result: dict[str, Any]
    if args.direct_local:
        if (
            args.authorization_file is None
            or not args.tenant_id
            or not args.request_id
            or not args.database_url
        ):
            result = {
                "schema_version": "research-v2-live-acceptance-report/2",
                "status": "BLOCKED",
                "execution_mode": "live",
                "external_io": False,
                "reason_codes": [
                    "LIVE_AUTHORIZATION_DATABASE_TENANT_REQUEST_REQUIRED"
                ],
            }
        else:
            try:
                validate_live_authorization(
                    args.authorization_file,
                    requested_budget_microunits=args.approved_budget_microunits,
                    requested_actions=("model_evaluation", "source_read"),
                    requested_case_ids=selected,
                    requested_tenant_id=args.tenant_id,
                )
                result = _run_async(
                    execute_direct_local_acceptance(
                        authorization_file=args.authorization_file,
                        tenant_id=args.tenant_id,
                        request_id=args.request_id,
                        case_ids=selected,
                        approved_budget_microunits=args.approved_budget_microunits,
                        database_url=args.database_url,
                        env_file=args.env_file,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - CLI 只输出稳定异常类型
                result = {
                    "schema_version": "research-v2-live-acceptance-report/2",
                    "status": "BLOCKED",
                    "execution_mode": "live",
                    "external_io": True,
                    "reason_codes": [type(exc).__name__],
                }
    elif args.live:
        if (
            args.authorization_file is None
            or not args.base_url
            or not args.tenant_id
            or not args.request_id
        ):
            result = {
                "schema_version": "research-v2-live-acceptance/1",
                "status": "BLOCKED",
                "execution_mode": "live",
                "external_io": False,
                "reason_codes": [
                    "LIVE_AUTHORIZATION_BASE_TENANT_REQUEST_REQUIRED"
                ],
            }
        else:
            try:
                auth = validate_live_authorization(
                    args.authorization_file,
                    requested_budget_microunits=args.approved_budget_microunits,
                    requested_actions=("model_evaluation", "source_read"),
                    requested_case_ids=selected,
                    requested_tenant_id=args.tenant_id,
                )
            except (TypeError, ValueError) as exc:
                result = {
                    "schema_version": "research-v2-live-acceptance/1",
                    "status": "BLOCKED",
                    "execution_mode": "live",
                    "external_io": False,
                    "reason_codes": [str(exc)],
                }
            else:
                try:
                    result = execute_live_acceptance(
                        base_url=args.base_url,
                        tenant_id=args.tenant_id,
                        request_id=args.request_id,
                        authorization_id=str(auth["authorization_id"]),
                        case_ids=selected,
                        approved_budget_microunits=int(
                            auth["approved_budget_microunits"]
                        ),
                        timeout_seconds=args.timeout_seconds,
                    )
                except LiveAcceptanceClientError as exc:
                    result = {
                        "schema_version": "research-v2-live-acceptance/1",
                        "status": "BLOCKED",
                        "execution_mode": "live",
                        "external_io": exc.request_attempted,
                        "authorization_id": auth["authorization_id"],
                        "approved_budget_microunits": auth[
                            "approved_budget_microunits"
                        ],
                        "reason_codes": [exc.reason_code],
                    }
    else:
        if len(selected) != 1:
            raise SystemExit("offline mode accepts exactly one recorded case")
        result = evaluate_offline_case(
            selected[0],
            PROJECT_ROOT
            / "docs/superpowers/sdd/intent-research-v2/task-X03-offline-evidence.json",
        )
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if result["status"] in {"PASS", "NOT_EXECUTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LIVE_CASES",
    "LiveAcceptanceClientError",
    "evaluate_offline_case",
    "execute_direct_local_acceptance",
    "execute_live_acceptance",
    "main",
    "validate_live_authorization",
]
