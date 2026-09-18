"""X05 单测试租户 20 请求真实灰度入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
for search_path in (PROJECT_ROOT, SOURCE_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from openai import AsyncOpenAI
from psycopg import AsyncConnection

from efficiency_platform_agent.capabilities.model.runtime import (  # type: ignore[import-untyped]
    ModelRuntime,
)
from efficiency_platform_agent.configuration.integration import (  # type: ignore[import-untyped]
    S7IntegrationSettings,
)
from efficiency_platform_agent.contracts.live_acceptance_v2 import (  # type: ignore[import-untyped]
    LIVE_ACCEPTANCE_CASE_PROMPTS,
    LiveAcceptanceRequestV1,
)
from efficiency_platform_agent.core.model import (  # type: ignore[import-untyped]
    ModelCandidate,
    ModelTier,
)
from efficiency_platform_agent.evaluation.live_canary_v2 import (  # type: ignore[import-untyped]
    execute_single_tenant_canary,
)
from efficiency_platform_agent.harness.live_acceptance import (  # type: ignore[import-untyped]
    JsonLiveAcceptanceAuthorizationStore,
    PostgresLiveAcceptanceBudgetBinder,
)
from efficiency_platform_agent.harness.live_research_v2 import (  # type: ignore[import-untyped]
    FreeSourceLiveAcceptanceRunner,
    LiveFreeSourceCollector,
)
from efficiency_platform_agent.providers.llm.deepseek import (  # type: ignore[import-untyped]
    DeepSeekModelProvider,
)
from efficiency_platform_agent.providers.llm.registry import (  # type: ignore[import-untyped]
    ModelProviderRegistry,
)
from efficiency_platform_agent.routing.model_router import (  # type: ignore[import-untyped]
    ModelPolicyRouter,
)


def _run_async(coroutine):
    if sys.platform == "win32":
        return asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(
                selectors.SelectSelector()
            ),
        )
    return asyncio.run(coroutine)


async def execute_canary(
    *,
    authorization_file: Path,
    tenant_id: str,
    request_id: str,
    approved_budget_microunits: int,
    database_url: str,
    env_file: Path,
) -> dict[str, object]:
    store = JsonLiveAcceptanceAuthorizationStore.from_files((authorization_file,))
    raw = json.loads(authorization_file.read_text(encoding="utf-8"))
    authorization = store.get(str(raw.get("authorization_id", "")))
    if authorization is None:
        raise ValueError("CANARY_AUTHORIZATION_NOT_FOUND")
    now = datetime.now(UTC)
    if not authorization.approved_at <= now < authorization.expires_at:
        raise ValueError("CANARY_AUTHORIZATION_EXPIRED")
    if tenant_id not in authorization.allowed_tenant_ids:
        raise ValueError("CANARY_TENANT_NOT_AUTHORIZED")
    required_actions = {
        "model_evaluation",
        "source_read",
        "research_acceptance",
        "single_tenant_canary",
    }
    if not required_actions.issubset(authorization.allowed_actions):
        raise ValueError("CANARY_ACTION_NOT_AUTHORIZED")
    if approved_budget_microunits > authorization.max_budget_microunits:
        raise ValueError("CANARY_BUDGET_NOT_AUTHORIZED")

    settings = S7IntegrationSettings.from_env_file(env_file)

    def required(name: str) -> str:
        value = getattr(settings, name)
        if value is None or not value.get_secret_value().strip():
            raise ValueError(f"LIVE_MODEL_CONFIGURATION_MISSING:{name}")
        return value.get_secret_value()

    client = AsyncOpenAI(
        api_key=required("deepseek_api_key"),
        base_url=required("deepseek_base_url"),
        timeout=120.0,
        max_retries=0,
    )
    model_id = required("deepseek_balanced_model")
    provider = DeepSeekModelProvider(
        SimpleNamespace(chat=client.chat, close=client.close),
        model_id,
        timeout_ms=120_000,
    )
    registry = ModelProviderRegistry()
    provider_id = "deepseek_live_x05_canary"
    registry.register(provider_id, provider)
    candidate = ModelCandidate(
        "deepseek-live-x05-canary",
        provider_id,
        model_id,
        ModelTier.BALANCED,
        True,
        False,
        64_000,
        True,
        False,
    )
    collector = LiveFreeSourceCollector()
    runner = FreeSourceLiveAcceptanceRunner(
        collector,
        ModelRuntime(ModelPolicyRouter((candidate,)), registry),
    )
    connection = await AsyncConnection.connect(database_url)
    try:
        request = LiveAcceptanceRequestV1(
            request_id=request_id,
            authorization_id=authorization.authorization_id,
            case_ids=tuple(LIVE_ACCEPTANCE_CASE_PROMPTS),
            requested_budget_microunits=approved_budget_microunits,
        )
        binder = PostgresLiveAcceptanceBudgetBinder(connection, "agent_runtime")
        binding = binder.bind(authorization, request, tenant_id=tenant_id)
        try:
            report = await execute_single_tenant_canary(
                runner=runner,
                binding=binding,
            )
            snapshot = await binding.port.snapshot(binding.scope)
            return {
                **report,
                "execution_mode": "live-single-tenant",
                "model_id": model_id,
                "approved_budget_microunits": approved_budget_microunits,
                "used_cost_microunits": snapshot.used.cost_microunits,
                "cost_observed": snapshot.used.cost_microunits > 0,
                "budget_usage": asdict(snapshot.used),
                "production_deployment_performed": False,
            }
        finally:
            await binding.port.mark_scope_terminal(binding.scope, "terminal")
    finally:
        await connection.close()
        await provider.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--approved-budget-microunits", type=int, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = _run_async(
            execute_canary(
                authorization_file=args.authorization_file,
                tenant_id=args.tenant_id,
                request_id=args.request_id,
                approved_budget_microunits=args.approved_budget_microunits,
                database_url=args.database_url,
                env_file=args.env_file,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI 不泄露 Provider 内容
        result = {
            "schema_version": "research-v2-live-canary/1",
            "status": "BLOCKED",
            "reason_codes": [type(exc).__name__],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result.get("status"),
        "valid_request_count": result.get("valid_request_count", 0),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
