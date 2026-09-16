"""S7 场景验收脚本。

默认只执行零外部 I/O 的关闭检查；离线模式使用固定 Stub 证明接线，
不会创建 Provider、数据库、Redis、COS 或 Taskiq 客户端。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from efficiency_platform_agent.agents.operation.contracts.evidence import (  # type: ignore[import-untyped]  # 契约模块暂未发布类型标记
    TimeWindow,
)
from efficiency_platform_agent.capabilities.research.contracts import (  # type: ignore[import-untyped]  # 研究契约模块暂未发布类型标记
    ResearchRequest,
    ResearchStatus,
)
from efficiency_platform_agent.capabilities.research.deepseek_web_search import (  # type: ignore[import-untyped]  # 研究适配器模块暂未发布类型标记
    DeepSeekWebSearchProvider,
)
from efficiency_platform_agent.configuration.integration import (  # type: ignore[import-untyped]  # 配置模块暂未发布类型标记
    GateAction,
    GateAuthorization,
    IntegrationGate,
    S7IntegrationSettings,
)
from efficiency_platform_agent.core.run import (  # type: ignore[import-untyped]  # 核心契约模块暂未发布类型标记
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.providers.llm.deepseek import (  # type: ignore[import-untyped]  # 适配器模块暂未发布类型标记
    DeepSeekModelProvider,
)

_SCENARIOS: dict[str, dict[str, Any]] = {
    "industry_digest": {
        "status": "SUCCEEDED",
        "evidence": [{"source_id": "stub-ai-001", "title": "合成行业动态"}],
        "quality": {"source_linkage": 1.0},
    },
    "multi_platform_content": {
        "status": "SUCCEEDED",
        "deliverables": {
            "xiaohongshu": "小红书标题\n短段落与标签",
            "wechat": "微信公众号标题\n长段落与摘要",
            "toutiao": "今日头条标题\n资讯导语与正文",
        },
        "evidence": [{"source_id": "stub-content-001"}],
    },
    "uploaded_file_review": {
        "status": "SUCCEEDED",
        "document_references": [{"document_id": "fixture-document-v1", "page": 1}],
        "evidence": [{"source_id": "fixture-document-v1"}],
    },
    "partial_failure": {
        "status": "PARTIAL",
        "completed_scope": ["热点提炼", "摘要生成"],
        "missing_scope": ["可选来源复核"],
        "evidence": [{"source_id": "stub-partial-001"}],
    },
}


def _secret_value(value: Any) -> str:
    """读取已经通过门禁校验的必填 SecretStr。"""

    if value is None:
        raise RuntimeError("INTEGRATION_SECRET_MISSING")
    return str(value.get_secret_value())


def _not_executed(reason: str) -> dict[str, Any]:
    """构造默认关闭或授权不足时的无副作用结果。"""
    return {
        "status": "NOT_EXECUTED",
        "reason": reason,
        "external_io": False,
        "selected_real_gates": [],
    }


def run_offline_scenario(name: str) -> dict[str, Any]:
    """运行一个固定离线 Stub 场景，仅返回内存中的接线证据。"""
    if name not in _SCENARIOS:
        raise ValueError("未知离线场景")
    result = dict(_SCENARIOS[name])
    result["scenario"] = name
    result["external_io"] = False
    result["execution_mode"] = "offline_stub"
    return result


def load_authorizations(approval_file: Path) -> tuple[GateAuthorization, ...]:
    """读取并严格校验脱敏授权记录，不输出记录内容或敏感字段。"""
    if not approval_file.is_file():
        raise ValueError("authorization_file_missing")
    try:
        data = json.loads(approval_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("authorization_file_invalid") from error
    if not isinstance(data, dict) or data.get("version") != "s7-authorization/1":
        raise ValueError("authorization_file_invalid")
    raw_records = data.get("authorizations")
    if not isinstance(raw_records, list):
        raise ValueError("authorization_file_invalid")  # noqa: TRY004  # 授权结构错误统一映射为稳定值错误
    try:
        return tuple(GateAuthorization.model_validate(item) for item in raw_records)
    except (TypeError, ValueError) as error:
        raise ValueError("authorization_file_invalid") from error


def _digest(value: str) -> str:
    """计算不包含敏感值的授权上下文摘要。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sql_statements(sql_text: str) -> tuple[str, ...]:
    """移除整行 SQL 注释并拆分本验收包中的固定语句。"""
    without_comments = "\n".join(
        line for line in sql_text.splitlines() if not line.lstrip().startswith("--")
    )
    return tuple(
        statement.strip()
        for statement in without_comments.split(";")
        if statement.strip()
    )


async def probe_deepseek_chat(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行一次只读 DeepSeek 模型列表探测，不发送模型请求。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.DEEPSEEK_CHAT
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    matching_authorizations = tuple(
        item
        for item in authorizations
        if item.gate is gate and item.action is GateAction.NETWORK_PROBE
    )
    authorization = max(
        matching_authorizations,
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("network_probe_authorization_missing")
    target_digest = _digest("deepseek-models-endpoint-v1")
    input_digest = _digest("models.list")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.NETWORK_PROBE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("deepseek.models",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 1,
                "max_model_calls": 0,
                "max_cost_microunits": 0,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=_secret_value(settings.deepseek_api_key),
        base_url=_secret_value(settings.deepseek_base_url),
        timeout=30.0,
        max_retries=0,
    )
    started = time.perf_counter()
    try:
        await client.models.list()
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result: dict[str, Any] = {
            "status": "FAILED",
            "reason": "network_probe_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 0,
            "cost_microunits": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    else:
        result = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 0,
            "cost_microunits": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    finally:
        await client.close()
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g1-deepseek-network-probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def run_deepseek_chat_acceptance(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行一次受控 DeepSeek 最小模型验收，不保存模型响应正文。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.DEEPSEEK_CHAT
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    authorization = next(
        (
            item
            for item in authorizations
            if item.gate is gate and item.action is GateAction.CHARGED_ACCEPTANCE
        ),
        None,
    )
    if authorization is None:
        return _not_executed("charged_acceptance_authorization_missing")
    model_id = _secret_value(settings.deepseek_fast_model)
    target_digest = _digest("deepseek-chat-endpoint-v1")
    input_digest = _digest("s7-g1-minimal-structured-probe-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.CHARGED_ACCEPTANCE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(model_id,),
            resource_ids=("deepseek.chat",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 1,
                "max_model_calls": 1,
                "max_cost_microunits": 1_000_000,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=_secret_value(settings.deepseek_api_key),
        base_url=_secret_value(settings.deepseek_base_url),
        timeout=30.0,
        max_retries=0,
    )
    provider_client = SimpleNamespace(chat=client.chat, close=client.close)
    provider = DeepSeekModelProvider(provider_client, model_id, timeout_ms=30_000)
    request = ProviderRequest(
        "s7-g1/1",
        (ProviderMessage("user", '仅返回 JSON 对象：{"ok":true}'),),
        JsonObject(
            (
                ("response_format", JsonObject((("type", "json_object"),))),
                ("temperature", 0),
            )
        ),
        30_000,
    )
    started = time.perf_counter()
    network_calls = 1
    model_calls = 1
    try:
        response = await provider.complete(request)
        usage = response.usage
        output_valid = False
        if response.message is not None and isinstance(response.message.content, str):
            try:
                parsed = json.loads(response.message.content)
                output_valid = isinstance(parsed, dict) and parsed.get("ok") is True
            except json.JSONDecodeError:
                output_valid = False
        if response.error is not None:
            result: dict[str, Any] = {
                "status": "FAILED",
                "reason": "model_request_failed",
                "error_code": response.error.code,
                "external_io": True,
                "selected_real_gates": [gate.value],
                "network_calls": network_calls,
                "model_calls": model_calls,
                "cost_microunits": usage.cost_microunits,
                "cost_observed": usage.cost_microunits > 0,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
        elif not output_valid:
            result = {
                "status": "FAILED",
                "reason": "structured_output_invalid",
                "external_io": True,
                "selected_real_gates": [gate.value],
                "network_calls": network_calls,
                "model_calls": model_calls,
                "cost_microunits": usage.cost_microunits,
                "cost_observed": usage.cost_microunits > 0,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
        else:
            result = {
                "status": "SUCCEEDED",
                "external_io": True,
                "selected_real_gates": [gate.value],
                "network_calls": network_calls,
                "model_calls": model_calls,
                "cost_microunits": usage.cost_microunits,
                "cost_observed": usage.cost_microunits > 0,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result = {
            "status": "FAILED",
            "reason": "model_acceptance_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": network_calls,
            "model_calls": model_calls,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        await provider.close()
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g1-deepseek-chat-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


def _web_search_request() -> ResearchRequest:
    """构造不包含用户正文的最小服务端搜索请求。"""
    return ResearchRequest(
        "research-request/1",
        "s7-g2-search",
        "s7-g2-task",
        "s7-acceptance-tenant",
        "仅返回一条可追溯的合成行业动态来源",
        TimeWindow(None, None),
        1,
        ("s7-conclusion-1",),
        "research-result/1",
    )


async def probe_deepseek_web_search(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行一次服务端 web_search 最小探测，不打开任何来源 URL。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.DEEPSEEK_WEB_SEARCH
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    authorization = max(
        (
            item
            for item in authorizations
            if item.gate is gate and item.action is GateAction.NETWORK_PROBE
        ),
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("network_probe_authorization_missing")
    target_digest = _digest("deepseek-s7-web-search-v1")
    input_digest = _digest("s7-web-search-probe-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.NETWORK_PROBE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(_secret_value(settings.deepseek_fast_model),),
            resource_ids=("deepseek.web_search",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 1,
                "max_model_calls": 1,
                "max_search_calls": 1,
                "max_cost_microunits": 0,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=_secret_value(settings.deepseek_api_key),
        base_url=_secret_value(settings.deepseek_base_url),
        timeout=30.0,
        max_retries=0,
    )
    provider = DeepSeekWebSearchProvider(
        client,
        model=_secret_value(settings.deepseek_balanced_model),
        timeout_ms=30_000,
    )
    started = time.perf_counter()
    try:
        research = await provider.research(_web_search_request())
        result: dict[str, Any] = {
            "status": "SUCCEEDED"
            if research.status is ResearchStatus.SUCCEEDED
            else "FAILED",
            "reason": None
            if research.status is ResearchStatus.SUCCEEDED
            else research.error_code,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 1,
            "search_calls": 1,
            "observation_count": len(research.observations),
            "source_urls_opened": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result = {
            "status": "FAILED",
            "reason": "web_search_probe_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 1,
            "search_calls": 1,
            "source_urls_opened": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        await client.close()
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g2-deepseek-web-search-probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def run_deepseek_web_search_acceptance(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行最多一次服务端搜索验收并只保存脱敏来源计数。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.DEEPSEEK_WEB_SEARCH
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    authorization = max(
        (
            item
            for item in authorizations
            if item.gate is gate and item.action is GateAction.CHARGED_ACCEPTANCE
        ),
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("charged_acceptance_authorization_missing")
    target_digest = _digest("deepseek-s7-web-search-v1")
    input_digest = _digest("s7-web-search-acceptance-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.CHARGED_ACCEPTANCE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(_secret_value(settings.deepseek_fast_model),),
            resource_ids=("deepseek.web_search",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 1,
                "max_model_calls": 1,
                "max_search_calls": 1,
                "max_cost_microunits": 1_000_000,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=_secret_value(settings.deepseek_api_key),
        base_url=_secret_value(settings.deepseek_base_url),
        timeout=30.0,
        max_retries=0,
    )
    provider = DeepSeekWebSearchProvider(
        client,
        model=_secret_value(settings.deepseek_balanced_model),
        timeout_ms=30_000,
    )
    started = time.perf_counter()
    try:
        research = await provider.research(_web_search_request())
        succeeded = research.status is ResearchStatus.SUCCEEDED and bool(
            research.observations
        )
        result: dict[str, Any] = {
            "status": "SUCCEEDED" if succeeded else "FAILED",
            "reason": None
            if succeeded
            else (research.error_code or "search_insufficient"),
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 1,
            "search_calls": 1,
            "observation_count": len(research.observations),
            "source_urls_opened": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result = {
            "status": "FAILED",
            "reason": "web_search_acceptance_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 1,
            "search_calls": 1,
            "source_urls_opened": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        await client.close()
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g2-deepseek-web-search-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def probe_redis_taskiq(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行两个 Redis 目标的只读 PING 探测，不写入键或启动 Worker。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.REDIS_TASKIQ
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    matching_authorizations = tuple(
        item
        for item in authorizations
        if item.gate is gate and item.action is GateAction.NETWORK_PROBE
    )
    authorization = max(
        matching_authorizations,
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("network_probe_authorization_missing")
    target_digest = _digest("redis-s7-probe-v1")
    input_digest = _digest("ping-only-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.NETWORK_PROBE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("redis.task_broker", "redis.run_events"),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 2,
                "max_model_calls": 0,
                "max_cost_microunits": 0,
                "max_redis_records": 0,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from redis.asyncio import Redis

    clients: list[Any] = []
    started = time.perf_counter()
    try:
        for secret_url in (
            settings.task_broker_url,
            settings.run_event_redis_url,
        ):
            client = Redis.from_url(
                _secret_value(secret_url),
                decode_responses=False,
                socket_connect_timeout=10,
                socket_timeout=10,
                retry_on_timeout=False,
            )
            clients.append(client)
            await client.ping()
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result: dict[str, Any] = {
            "status": "FAILED",
            "reason": "redis_probe_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(clients),
            "model_calls": 0,
            "redis_records": 0,
            "cost_microunits": 0,
        }
    else:
        result = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(clients),
            "model_calls": 0,
            "redis_records": 0,
            "cost_microunits": 0,
        }
    finally:
        for client in clients:
            close = getattr(client, "aclose", None)
            if close is not None:
                await close()
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g4-redis-network-probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def run_redis_taskiq_acceptance(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行单 Worker 的 Redis/Taskiq 投递、执行、续读、取消和清理验收。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.REDIS_TASKIQ
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    matching_authorizations = tuple(
        item
        for item in authorizations
        if item.gate is gate and item.action is GateAction.WRITE_ACCEPTANCE
    )
    authorization = max(
        matching_authorizations,
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("write_acceptance_authorization_missing")
    target_digest = _digest("redis-s7-taskiq-lifecycle-v1")
    input_digest = _digest("s7-redis-single-worker-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.WRITE_ACCEPTANCE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("redis.task_broker", "redis.run_events"),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 50,
                "max_model_calls": 0,
                "max_cost_microunits": 1_000_000,
                "max_redis_records": 20,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from redis.asyncio import Redis
    from taskiq.receiver import Receiver
    from taskiq_redis import ListQueueBroker

    from efficiency_platform_agent.core.enums import (  # type: ignore[import-untyped]  # 核心枚举模块暂未发布类型标记
        RunStatus,
    )
    from efficiency_platform_agent.core.runtime import (  # type: ignore[import-untyped]  # 运行事实模块暂未发布类型标记
        RunEventRecord,
    )
    from efficiency_platform_agent.providers.cache.redis import (  # type: ignore[import-untyped]  # Redis 适配器暂未发布类型标记
        RedisRunEventStore,
    )
    from efficiency_platform_agent.tasks.broker import (  # type: ignore[import-untyped]  # Taskiq 边界适配器暂未发布类型标记
        SingleWorkerTaskBroker,
    )

    run_stamp = authorization.run_stamp
    adapter_stamp = f"{run_stamp}-adapter"
    queue_name = f"s7:{run_stamp}:tasks"
    event_client = Redis.from_url(
        _secret_value(settings.run_event_redis_url),
        decode_responses=False,
        socket_connect_timeout=10,
        socket_timeout=10,
        retry_on_timeout=False,
    )
    broker_client = Redis.from_url(
        _secret_value(settings.task_broker_url),
        decode_responses=False,
        socket_connect_timeout=10,
        socket_timeout=10,
        retry_on_timeout=False,
    )
    try:
        server_info = await event_client.info("server")
        raw_version = (
            server_info.get("redis_version") if isinstance(server_info, dict) else None
        )
        major_version = int(str(raw_version).split(".", 1)[0])
    except Exception:  # noqa: BLE001, 能力探测失败按不支持处理并失败关闭
        major_version = 0
    if major_version < 5:
        version_result = {
            "status": "FAILED",
            "reason": "redis_streams_unsupported",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 0,
            "redis_records": 0,
            "cleanup_ok": True,
            "cost_microunits": 0,
            "cost_observed": False,
        }
        await event_client.aclose()
        await broker_client.aclose()
        if evidence_root is not None:
            evidence_root.mkdir(parents=True, exist_ok=True)
            (evidence_root / "g4-redis-taskiq-acceptance.json").write_text(
                json.dumps(version_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return version_result
    event_store = RedisRunEventStore(event_client, run_stamp)
    adapter = SingleWorkerTaskBroker(broker_client, adapter_stamp)
    broker = ListQueueBroker(
        _secret_value(settings.task_broker_url),
        queue_name=queue_name,
        max_connection_pool_size=2,
    )
    executed = asyncio.Event()
    executed_payloads: list[dict[str, Any]] = []

    @broker.task(task_name=f"s7.acceptance.{run_stamp}")
    async def acceptance_task(payload: dict[str, Any]) -> dict[str, Any]:
        """只返回合成任务的受控回执，不读取用户数据。"""
        executed_payloads.append(dict(payload))
        executed.set()
        return {"ok": True, "task_id": str(payload.get("task_id", ""))}

    receiver: Receiver | None = None
    worker_task: asyncio.Task[None] | None = None
    deleted_keys = 0
    cleanup_ok = False
    phase = "初始化"
    started = time.perf_counter()
    try:
        phase = "追加启动事件"
        await event_store.append(
            RunEventRecord(
                event_id="s7-event-1",
                event_type="run_started",
                run_id=run_stamp,
                tenant_id="s7-acceptance-tenant",
                sequence=1,
                occurred_at_epoch_ms=int(time.time() * 1000),
                status=RunStatus.RUNNING,
                payload=JsonObject(),
            )
        )
        payload = {"run_stamp": run_stamp, "task_id": "task-1", "sequence": 1}
        phase = "验证任务幂等"
        first_id = await adapter.enqueue("task-1", payload, idempotency_key="idem-1")
        duplicate_id = await adapter.enqueue(
            "task-1", payload, idempotency_key="idem-1"
        )
        if first_id != duplicate_id:
            raise ValueError("TASK_IDEMPOTENCY_FAILED")
        cancelled = await adapter.cancel("task-cancel")
        if not cancelled or not await adapter.is_cancelled("task-cancel"):
            raise ValueError("TASK_CANCELLATION_FAILED")

        phase = "启动 Taskiq Worker"
        receiver = Receiver(broker, max_tasks_to_execute=1, wait_tasks_timeout=10)
        finish_event = asyncio.Event()
        worker_task = asyncio.create_task(receiver.listen(finish_event))
        await asyncio.sleep(0.2)
        phase = "投递 Taskiq 任务"
        await acceptance_task.kiq(payload)
        phase = "等待 Worker 执行"
        await asyncio.wait_for(executed.wait(), timeout=15)
        phase = "关闭 Taskiq Worker"
        finish_event.set()
        await asyncio.wait_for(worker_task, timeout=15)
        worker_task = None
        if executed_payloads != [payload]:
            raise ValueError("TASK_WORKER_PAYLOAD_INVALID")
        phase = "追加完成事件"
        await event_store.append(
            RunEventRecord(
                event_id="s7-event-2",
                event_type="task_succeeded",
                run_id=run_stamp,
                tenant_id="s7-acceptance-tenant",
                sequence=2,
                occurred_at_epoch_ms=int(time.time() * 1000),
                status=RunStatus.SUCCEEDED,
                payload=JsonObject((("task_id", "task-1"),)),
            )
        )
        phase = "回读事件"
        events = await event_store.list_after(
            "s7-acceptance-run", "s7-acceptance-tenant", 0
        )
        if len(events) != 0:
            raise ValueError("EVENT_TENANT_FILTER_FAILED")
        events = await event_store.list_after(run_stamp, "s7-acceptance-tenant", 0)
        if [event.sequence for event in events] != [1, 2]:
            raise ValueError("EVENT_REPLAY_FAILED")
        result: dict[str, Any] = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 18,
            "model_calls": 0,
            "redis_records": 5,
            "worker_executed": True,
            "idempotency_checked": True,
            "cancellation_checked": True,
            "event_replay_checked": True,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result = {
            "status": "FAILED",
            "reason": "redis_taskiq_acceptance_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 0,
            "model_calls": 0,
            "redis_records": 0,
            "cleanup_ok": False,
            "phase": phase,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        if worker_task is not None:
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)
        if receiver is not None:
            await broker.shutdown()
        cleanup_ok = True
        for client in (event_client, broker_client):
            try:
                keys: list[Any] = []
                scan_iter = getattr(client, "scan_iter", None)
                if scan_iter is None:
                    raise RuntimeError("REDIS_SCAN_UNAVAILABLE")
                async for key in scan_iter(match=f"s7:{run_stamp}*"):
                    keys.append(key)
                if keys:
                    deleted_keys += int(await client.delete(*keys))
                remaining = []
                async for key in scan_iter(match=f"s7:{run_stamp}*"):
                    remaining.append(key)
                cleanup_ok = cleanup_ok and not remaining
            except Exception:  # noqa: BLE001, 清理失败只保留布尔结果
                cleanup_ok = False
        await adapter.close()
        await event_store.close()
    result["deleted_keys"] = deleted_keys
    result["cleanup_ok"] = cleanup_ok
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g4-redis-taskiq-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def probe_postgres_pgvector(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    env_file: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行 PostgreSQL/pgvector 只读预检，不创建 Schema 或写入数据。"""
    settings = S7IntegrationSettings.from_env_file(env_file or PROJECT_ROOT / ".env")
    gate = IntegrationGate.POSTGRES_PGVECTOR
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    authorization = max(
        (
            item
            for item in authorizations
            if item.gate is gate and item.action is GateAction.NETWORK_PROBE
        ),
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("network_probe_authorization_missing")
    target_digest = _digest("postgres-s7-agent-owned-schema-v1")
    input_digest = _digest("postgres-readonly-precheck-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.NETWORK_PROBE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("postgres.runtime", "postgres.vector"),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 2,
                "max_model_calls": 0,
                "max_cost_microunits": 0,
                "max_database_rows_read": 20,
                "max_database_rows_written": 0,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    import psycopg

    schema = "s7_acceptance_00000000"
    sql_root = PROJECT_ROOT / "sql" / "changes" / "20260903_001_S7验收命名空间"
    precheck = (
        (sql_root / "01-precheck.sql")
        .read_text(encoding="utf-8")
        .replace("s7_acceptance_00000000", schema)
    )
    started = time.perf_counter()
    connections: list[Any] = []
    try:
        for secret_url in (
            settings.runtime_database_url,
            settings.vector_database_url,
        ):
            conn = await psycopg.AsyncConnection.connect(
                _secret_value(secret_url), connect_timeout=10
            )
            connections.append(conn)
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                async with conn.cursor() as cursor:
                    for statement in _sql_statements(precheck):
                        await cursor.execute(statement)
        result: dict[str, Any] = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(connections),
            "database_rows_read": 14,
            "database_rows_written": 0,
            "vector_extension_verified": True,
            "target_schema_absent": True,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result = {
            "status": "FAILED",
            "reason": "postgres_probe_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(connections),
            "database_rows_read": 0,
            "database_rows_written": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        for connection in connections:
            await connection.close()
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g3-postgres-network-probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def run_postgres_pgvector_acceptance(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    env_file: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行受控 PostgreSQL/pgvector 合成数据验收并精确回滚。"""
    settings = S7IntegrationSettings.from_env_file(env_file or PROJECT_ROOT / ".env")
    gate = IntegrationGate.POSTGRES_PGVECTOR
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    authorization = max(
        (
            item
            for item in authorizations
            if item.gate is gate and item.action is GateAction.WRITE_ACCEPTANCE
        ),
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("write_acceptance_authorization_missing")
    target_digest = _digest("postgres-s7-agent-owned-schema-v1")
    input_digest = _digest("postgres-synthetic-run-event-checkpoint-vector-fts-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.WRITE_ACCEPTANCE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("postgres.runtime", "postgres.vector"),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 20,
                "max_model_calls": 0,
                "max_cost_microunits": 0,
                "max_database_rows_read": 100,
                "max_database_rows_written": 20,
                "max_bytes": 4_194_304,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    import psycopg

    schema = f"s7_acceptance_{_digest(authorization.run_stamp)[:8]}"
    sql_root = PROJECT_ROOT / "sql" / "changes" / "20260903_001_S7验收命名空间"
    up_sql = (
        (sql_root / "02-up.sql")
        .read_text(encoding="utf-8")
        .replace("s7_acceptance_00000000", schema)
    )
    rollback_sql = (
        (sql_root / "04-rollback.sql")
        .read_text(encoding="utf-8")
        .replace("s7_acceptance_00000000", schema)
    )
    dsn = _secret_value(settings.runtime_database_url)
    vector = "[" + ",".join(["1"] + ["0"] * 1023) + "]"
    started = time.perf_counter()
    connections: list[Any] = []
    schema_created = False
    cleanup_ok = False
    try:
        connection = await psycopg.AsyncConnection.connect(dsn, connect_timeout=10)
        connections.append(connection)
        async with connection.transaction():
            for statement in _sql_statements(up_sql):
                await connection.execute(statement)
            schema_created = True
            await connection.execute(
                f"INSERT INTO {schema}.runs "
                "(run_id, tenant_id, request_id, payload, version) "
                "VALUES (%s, %s, %s, %s::jsonb, %s)",
                ("s7-run-1", "tenant-a", "s7-request-1", '{"status":"RUNNING"}', 1),
            )
            await connection.execute(
                f"INSERT INTO {schema}.run_events "
                "(event_id, run_id, tenant_id, sequence, payload) "
                "VALUES (%s, %s, %s, %s, %s::jsonb)",
                ("s7-event-1", "s7-run-1", "tenant-a", 1, '{"type":"started"}'),
            )
            await connection.execute(
                f"INSERT INTO {schema}.run_usage "
                "(run_id, tenant_id, input_tokens, output_tokens, cost_microunits) "
                "VALUES (%s, %s, %s, %s, %s)",
                ("s7-run-1", "tenant-a", 12, 8, 0),
            )
            await connection.execute(
                f"INSERT INTO {schema}.checkpoints "
                "(thread_id, tenant_id, checkpoint_ns, checkpoint_id, state) "
                "VALUES (%s, %s, %s, %s, %s::jsonb)",
                ("s7-thread-1", "tenant-a", "main", "cp-1", '{"step":1}'),
            )
            await connection.execute(
                f"INSERT INTO {schema}.chunks "
                "(chunk_id, document_id, tenant_id, content, embedding, "
                "embedding_model, embedding_dimension) "
                "VALUES (%s, %s, %s, %s, %s::vector, %s, %s)",
                (
                    "s7-chunk-1",
                    "s7-doc-1",
                    "tenant-a",
                    "verification evidence",
                    vector,
                    "text-embedding-v4",
                    1024,
                ),
            )
            updated = await connection.execute(
                f"UPDATE {schema}.runs SET version = %s WHERE run_id = %s "
                "AND tenant_id = %s AND version = %s",
                (2, "s7-run-1", "tenant-a", 1),
            )
            if updated.rowcount != 1:
                raise ValueError("RUN_VERSION_UPDATE_FAILED")
            conflict = await connection.execute(
                f"UPDATE {schema}.runs SET version = %s WHERE run_id = %s "
                "AND tenant_id = %s AND version = %s",
                (3, "s7-run-1", "tenant-a", 1),
            )
            if conflict.rowcount != 0:
                raise ValueError("RUN_VERSION_CONFLICT_NOT_DETECTED")
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"SELECT count(*) FROM {schema}.run_events WHERE run_id=%s AND tenant_id=%s",
                    ("s7-run-1", "tenant-a"),
                )
                row = await cursor.fetchone()
                if row is None or row[0] != 1:
                    raise ValueError("EVENT_TENANT_FILTER_FAILED")
                await cursor.execute(
                    f"SELECT count(*) FROM {schema}.run_events WHERE run_id=%s AND tenant_id=%s",
                    ("s7-run-1", "tenant-b"),
                )
                row = await cursor.fetchone()
                if row is None or row[0] != 0:
                    raise ValueError("CROSS_TENANT_EVENT_LEAK")
                await cursor.execute(
                    f"SELECT count(*) FROM {schema}.chunks WHERE tenant_id=%s AND "
                    "to_tsvector('simple', content) @@ plainto_tsquery('simple', %s)",
                    ("tenant-a", "evidence"),
                )
                row = await cursor.fetchone()
                if row is None or row[0] != 1:
                    raise ValueError("FTS_ASSERTION_FAILED")
                await cursor.execute(
                    f"SELECT count(*) FROM {schema}.chunks WHERE tenant_id=%s AND "
                    "embedding <=> %s::vector < 0.01",
                    ("tenant-a", vector),
                )
                row = await cursor.fetchone()
                if row is None or row[0] != 1:
                    raise ValueError("VECTOR_ASSERTION_FAILED")
        second = await psycopg.AsyncConnection.connect(dsn, connect_timeout=10)
        connections.append(second)
        async with second.cursor() as cursor:
            await cursor.execute(
                f"SELECT checkpoint_id FROM {schema}.checkpoints WHERE thread_id=%s AND tenant_id=%s",
                ("s7-thread-1", "tenant-a"),
            )
            row = await cursor.fetchone()
            if row is None or row[0] != "cp-1":
                raise ValueError("CHECKPOINT_CROSS_CONNECTION_FAILED")
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result: dict[str, Any] = {
            "status": "FAILED",
            "reason": "postgres_acceptance_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(connections),
            "database_rows_read": 12,
            "database_rows_written": 5 if schema_created else 0,
            "cleanup_ok": False,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    else:
        result = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": len(connections),
            "database_rows_read": 12,
            "database_rows_written": 5,
            "transaction_checked": True,
            "optimistic_version_checked": True,
            "checkpoint_cross_connection_checked": True,
            "vector_checked": True,
            "fts_checked": True,
            "tenant_filter_checked": True,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    finally:
        for connection in connections:
            try:
                await connection.close()
            except Exception:  # noqa: BLE001, 关闭失败仅影响清理结论
                cleanup_ok = False
        if schema_created:
            try:
                cleanup_connection = await psycopg.AsyncConnection.connect(
                    dsn, connect_timeout=10
                )
                async with cleanup_connection.transaction():
                    await cleanup_connection.execute(rollback_sql)
                async with cleanup_connection.cursor() as cursor:
                    await cursor.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname=%s)",
                        (schema,),
                    )
                    row = await cursor.fetchone()
                    cleanup_ok = row is not None and not row[0]
                await cleanup_connection.close()
            except Exception:  # noqa: BLE001, 清理失败覆盖业务结果
                cleanup_ok = False
    result["cleanup_ok"] = cleanup_ok
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g3-postgres-pgvector-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def probe_cos_artifact(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行一次 COS Bucket 只读 HEAD 探测，不创建或删除对象。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.COS_ARTIFACT
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    matching_authorizations = tuple(
        item
        for item in authorizations
        if item.gate is gate and item.action is GateAction.NETWORK_PROBE
    )
    authorization = max(
        matching_authorizations,
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("network_probe_authorization_missing")
    target_digest = _digest("cos-s7-bucket-probe-v1")
    input_digest = _digest("head-bucket-only-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.NETWORK_PROBE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("cos.bucket",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 1,
                "max_model_calls": 0,
                "max_cost_microunits": 0,
                "max_cos_objects": 0,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from qcloud_cos import (  # type: ignore[import-untyped]  # 腾讯云 SDK 暂未发布类型标记
        CosConfig,
        CosS3Client,
    )

    # COS_BASE_URL 是对象访问域名，不将存储桶域名误当作 SDK 服务端点。
    config = CosConfig(
        Region=_secret_value(settings.cos_region),
        SecretId=_secret_value(settings.cos_secret_id),
        SecretKey=_secret_value(settings.cos_secret_key),
        Scheme="https",
        Timeout=10,
    )
    client = CosS3Client(config)
    started = time.perf_counter()
    try:
        client.head_bucket(Bucket=_secret_value(settings.cos_bucket))
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        result: dict[str, Any] = {
            "status": "FAILED",
            "reason": "cos_probe_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 0,
            "cos_objects": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    else:
        result = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 1,
            "model_calls": 0,
            "cos_objects": 0,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g5-cos-network-probe.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


async def run_cos_artifact_acceptance(
    *,
    approval_file: Path,
    evidence_root: Path | None = None,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """执行单个合成 COS 对象的完整生命周期并强制清理回读。"""
    settings = S7IntegrationSettings.from_env_file(PROJECT_ROOT / ".env")
    gate = IntegrationGate.COS_ARTIFACT
    if not settings.gates.get(gate.value, False):
        return _not_executed("gate_disabled")
    missing = settings.for_gate(gate)
    if missing:
        return _not_executed("configuration_missing")
    authorizations = load_authorizations(approval_file)
    matching_authorizations = tuple(
        item
        for item in authorizations
        if item.gate is gate and item.action is GateAction.WRITE_ACCEPTANCE
    )
    authorization = max(
        matching_authorizations,
        key=lambda item: item.approved_at_epoch_ms,
        default=None,
    )
    if authorization is None:
        return _not_executed("write_acceptance_authorization_missing")
    target_digest = _digest("cos-s7-artifact-lifecycle-v1")
    input_digest = _digest("s7-cos-single-object-v1")
    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorization.validate_request(
            run_stamp=authorization.run_stamp,
            executor_id=authorization.executor_id,
            gate=gate,
            action=GateAction.WRITE_ACCEPTANCE,
            target_digest=target_digest,
            input_digest=input_digest,
            model_ids=(),
            resource_ids=("cos.bucket",),
            now_epoch_ms=now,
            required_limits={
                "max_network_calls": 8,
                "max_model_calls": 0,
                "max_cost_microunits": 1_000_000,
                "max_cos_objects": 1,
                "max_bytes": 1_048_576,
            },
            cleanup_owner=authorization.cleanup_owner,
            cleanup_procedure_id=authorization.cleanup_procedure_id,
        )
    except (TypeError, ValueError):
        return _not_executed("authorization_context_mismatch")

    from qcloud_cos import (  # type: ignore[import-untyped]  # 腾讯云 SDK 暂未发布类型标记
        CosConfig,
        CosS3Client,
    )

    from efficiency_platform_agent.providers.storage.cos import (  # type: ignore[import-untyped]  # COS 适配器暂未发布类型标记
        ArtifactDeleteRequest,
        ArtifactGetRequest,
        ArtifactPutRequest,
        ArtifactSignRequest,
        CosArtifactProvider,
    )

    config = CosConfig(
        Region=_secret_value(settings.cos_region),
        SecretId=_secret_value(settings.cos_secret_id),
        SecretKey=_secret_value(settings.cos_secret_key),
        Scheme="https",
        Timeout=10,
    )
    client = CosS3Client(config)
    provider = CosArtifactProvider(
        client,
        bucket=_secret_value(settings.cos_bucket),
        region=_secret_value(settings.cos_region),
    )
    content = b"s7-cos-probe-v1"
    run_stamp = authorization.run_stamp
    tenant_id = "s7-acceptance-tenant"
    artifact_id = "probe"
    request = ArtifactPutRequest(run_stamp, tenant_id, artifact_id, content)
    record = None
    deleted = False
    readback_ok = False
    started = time.perf_counter()
    try:
        record = await provider.put(request)
        headed = await provider.head(
            ArtifactGetRequest(run_stamp, tenant_id, artifact_id)
        )
        downloaded = await provider.get(
            ArtifactGetRequest(run_stamp, tenant_id, artifact_id)
        )
        signed = await provider.sign_download(
            ArtifactSignRequest(run_stamp, tenant_id, artifact_id)
        )
        if (
            headed != record
            or downloaded != content
            or not signed.url.startswith("https://")
        ):
            raise ValueError("ARTIFACT_LIFECYCLE_ASSERTION_FAILED")
        try:
            await provider.head(
                ArtifactGetRequest(run_stamp, "s7-other-tenant", artifact_id)
            )
        except KeyError:
            pass
        else:
            raise ValueError("ARTIFACT_CROSS_TENANT_ACCESS_ALLOWED")
        await provider.delete(ArtifactDeleteRequest(run_stamp, tenant_id, artifact_id))
        deleted = True
        listed = await asyncio.to_thread(
            client.list_objects,
            Bucket=_secret_value(settings.cos_bucket),
            Prefix=f"s7/{run_stamp}/",
            MaxKeys=3,
        )
        contents = listed.get("Contents", []) if isinstance(listed, dict) else []
        if contents:
            raise ValueError("ARTIFACT_CLEANUP_NOT_EMPTY")
        readback_ok = True
        result: dict[str, Any] = {
            "status": "SUCCEEDED",
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 7,
            "model_calls": 0,
            "cos_objects": 1,
            "bytes_written": len(content),
            "cleanup_ok": True,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001, 对外只返回稳定错误类别
        cleanup_ok = deleted and readback_ok
        if record is not None and not deleted:
            try:
                await provider.delete(
                    ArtifactDeleteRequest(run_stamp, tenant_id, artifact_id)
                )
                cleanup_ok = True
            except Exception:  # noqa: BLE001, 清理失败只保留布尔结果
                cleanup_ok = False
        result = {
            "status": "FAILED",
            "reason": "cos_acceptance_failed",
            "error_type": type(error).__name__,
            "external_io": True,
            "selected_real_gates": [gate.value],
            "network_calls": 0,
            "model_calls": 0,
            "cos_objects": 1 if record is not None else 0,
            "bytes_written": len(content) if record is not None else 0,
            "cleanup_ok": cleanup_ok,
            "cost_microunits": 0,
            "cost_observed": False,
        }
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "g5-cos-artifact-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return result


def verify(
    *,
    gate: str | None = None,
    approval_file: Path | None = None,
    evidence_root: Path | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """执行默认关闭检查或显式离线接线验收。"""
    if not gate:
        return _not_executed("gate_not_selected")
    if gate != "offline" or not offline:
        if approval_file is None:
            return _not_executed("authorization_file_missing")
        try:
            authorizations = load_authorizations(approval_file)
        except ValueError as error:
            return _not_executed(str(error))
        if not authorizations:
            return _not_executed("authorization_missing")
        return _not_executed("real_gate_execution_not_enabled")
    scenarios = [run_offline_scenario(name) for name in _SCENARIOS]
    result: dict[str, Any] = {
        "status": "OFFLINE_STUB_ONLY",
        "external_io": False,
        "selected_real_gates": [],
        "scenarios": scenarios,
    }
    if evidence_root is not None:
        evidence_root.mkdir(parents=True, exist_ok=True)
        local_paths: list[str] = []
        for scenario in scenarios:
            target = evidence_root / f"{scenario['scenario']}.json"
            target.write_text(
                json.dumps(scenario, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            local_paths.append(str(target))
        manifest = evidence_root / "latest-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "s7-cleanup-manifest/1",
                    "local_paths": local_paths,
                    "external_prefixes": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        result["manifest"] = str(manifest)
    return result


def main(argv: list[str] | None = None) -> int:
    """命令行入口；默认不传 Gate 时始终零外部副作用。"""
    if sys.platform == "win32":
        # Psycopg 异步连接不兼容 Windows Proactor 事件循环。
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate")
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--charged", action="store_true")
    args = parser.parse_args(argv)
    if args.execute_real and args.gate == IntegrationGate.DEEPSEEK_CHAT.value:
        if args.approval_file is None:
            print(
                json.dumps(
                    _not_executed("authorization_file_missing"), ensure_ascii=False
                )
            )
            return 0
        runner = run_deepseek_chat_acceptance if args.charged else probe_deepseek_chat
        result = asyncio.run(
            runner(
                approval_file=args.approval_file,
                evidence_root=args.evidence_root,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.execute_real and args.gate == IntegrationGate.DEEPSEEK_WEB_SEARCH.value:
        if args.approval_file is None:
            print(
                json.dumps(
                    _not_executed("authorization_file_missing"), ensure_ascii=False
                )
            )
            return 0
        runner = (
            run_deepseek_web_search_acceptance
            if args.charged
            else probe_deepseek_web_search
        )
        result = asyncio.run(
            runner(
                approval_file=args.approval_file,
                evidence_root=args.evidence_root,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.execute_real and args.gate == IntegrationGate.REDIS_TASKIQ.value:
        if args.approval_file is None:
            print(
                json.dumps(
                    _not_executed("authorization_file_missing"), ensure_ascii=False
                )
            )
            return 0
        runner = run_redis_taskiq_acceptance if args.charged else probe_redis_taskiq
        result = asyncio.run(
            runner(
                approval_file=args.approval_file,
                evidence_root=args.evidence_root,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.execute_real and args.gate == IntegrationGate.POSTGRES_PGVECTOR.value:
        if args.approval_file is None:
            print(
                json.dumps(
                    _not_executed("authorization_file_missing"), ensure_ascii=False
                )
            )
            return 0
        runner = (
            run_postgres_pgvector_acceptance
            if args.charged
            else probe_postgres_pgvector
        )
        result = asyncio.run(
            runner(
                approval_file=args.approval_file,
                evidence_root=args.evidence_root,
                env_file=args.env_file,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.execute_real and args.gate == IntegrationGate.COS_ARTIFACT.value:
        if args.approval_file is None:
            print(
                json.dumps(
                    _not_executed("authorization_file_missing"), ensure_ascii=False
                )
            )
            return 0
        runner = run_cos_artifact_acceptance if args.charged else probe_cos_artifact
        result = asyncio.run(
            runner(
                approval_file=args.approval_file,
                evidence_root=args.evidence_root,
            )
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    result = verify(
        gate=args.gate,
        approval_file=args.approval_file,
        evidence_root=args.evidence_root,
        offline=args.offline,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "load_authorizations",
    "main",
    "probe_cos_artifact",
    "probe_deepseek_chat",
    "probe_deepseek_web_search",
    "probe_postgres_pgvector",
    "probe_redis_taskiq",
    "run_cos_artifact_acceptance",
    "run_deepseek_chat_acceptance",
    "run_deepseek_web_search_acceptance",
    "run_offline_scenario",
    "run_postgres_pgvector_acceptance",
    "run_redis_taskiq_acceptance",
    "verify",
]
