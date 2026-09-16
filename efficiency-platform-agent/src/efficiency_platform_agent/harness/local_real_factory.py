"""本地真实 DeepSeek 联调的显式组合根。"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
)
from efficiency_platform_agent.api.app import create_app
from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
from efficiency_platform_agent.capabilities.research.deepseek_web_search import (
    DeepSeekWebSearchProvider,
)
from efficiency_platform_agent.configuration.integration import (
    IntegrationGate,
    S7IntegrationSettings,
)
from efficiency_platform_agent.conversation.direct_submission import (
    DirectConversationSubmissionStore,
)
from efficiency_platform_agent.conversation.service import (
    ConversationService,
    ConversationSubmissionStore,
)
from efficiency_platform_agent.core.budget import BudgetGuard
from efficiency_platform_agent.core.diagnostics import NoopDiagnosticRecorder
from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
from efficiency_platform_agent.core.ports import ModelProvider
from efficiency_platform_agent.core.run import ExecutionBudget
from efficiency_platform_agent.harness.operation_agent_factory import (
    build_operation_agent,
)
from efficiency_platform_agent.observability.local_execution_log import (
    LocalExecutionLogger,
)
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    build_conversation_direct_registration,
)
from efficiency_platform_agent.orchestration.builders.operation_runtime import (
    build_operation_multi_agent_registration,
)
from efficiency_platform_agent.orchestration.cancellation import (
    InMemoryCancellationSignal,
)
from efficiency_platform_agent.orchestration.intent_interpreter import IntentInterpreter
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime
from efficiency_platform_agent.orchestration.scenario_resolver import ScenarioResolver
from efficiency_platform_agent.persistence.in_memory import (
    InMemoryRunEventStore,
    InMemoryRunRepository,
)
from efficiency_platform_agent.providers.deepseek_stream import (
    DeepSeekStreamingProvider,
)
from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
from efficiency_platform_agent.routing.model_router import ModelPolicyRouter
from efficiency_platform_agent.routing.strategy_router import StrategyRouter
from efficiency_platform_agent.runtime.event_hub import EventHub

from .service import AgentRuntimeService

# 运营多平台生成单节点允许 120 秒，HTTP Provider 上限必须与之对齐。
_OPERATION_MODEL_TIMEOUT_MS = 120_000


class _SystemClock:
    """本地服务使用的毫秒时钟。"""

    def now_epoch_ms(self) -> int:
        return int(time.time() * 1000)


class _UuidGenerator:
    """生成进程内不重复且不包含用户正文的标识。"""

    def new_run_id(self) -> str:
        return f"run-{uuid.uuid4().hex}"

    def new_event_id(self) -> str:
        return f"event-{uuid.uuid4().hex}"


class _RunScopedModelCancellation:
    """为共享模型运行时提供按异步调用隔离的 Run 取消探针。"""

    def __init__(self, cancellation: InMemoryCancellationSignal) -> None:
        self.cancellation = cancellation
        self.run_id: ContextVar[str | None] = ContextVar("model_run_id", default=None)

    @contextmanager
    def bind(self, run_id: str) -> Iterator[None]:
        """只在当前模型调用链绑定 Run，退出后恢复前一上下文。"""
        token = self.run_id.set(run_id)
        try:
            yield
        finally:
            self.run_id.reset(token)

    async def wait_requested(self) -> bool:
        """非阻塞读取当前 Run 的既有取消状态。"""
        run_id = self.run_id.get()
        return run_id is not None and await self.cancellation.is_requested(run_id)


@dataclass(slots=True)
class LocalAgentApplication:
    """持有应用、运行服务及由组合根创建的 HTTP 客户端。"""

    app: FastAPI
    runtime: AgentRuntimeService
    conversation: ConversationService
    event_hub: EventHub
    http_client: Any | None = None
    research_client: Any | None = None

    async def close(self) -> None:
        """等待后台任务并关闭组合根拥有的客户端。"""
        await self.runtime.wait_for_background_tasks()
        if self.http_client is not None:
            await self.http_client.aclose()
        if self.research_client is not None:
            close = getattr(self.research_client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result


def _secret(settings: S7IntegrationSettings, name: str) -> str:
    value = getattr(settings, name)
    if value is None or not value.get_secret_value().strip():
        raise ValueError(f"缺少本地真实运行配置: {name}")
    return value.get_secret_value()


def _candidate(candidate_id: str, provider_id: str, model: str, tier: ModelTier):
    return ModelCandidate(
        candidate_id,
        provider_id,
        model,
        tier,
        True,
        False,
        64_000,
        True,
        True,
    )


def build_local_agent_application(
    settings: S7IntegrationSettings | None = None,
    *,
    env_file: str | Path = ".env",
    provider: ModelProvider | None = None,
    test_mode: bool = False,
    http_client: Any | None = None,
    research_provider: Any | None = None,
) -> LocalAgentApplication:
    """默认装配真实 DeepSeek；Fake Provider 必须显式开启测试模式。"""
    if provider is not None and not test_mode:
        raise ValueError("自定义 Provider 仅允许显式测试模式")
    if research_provider is not None and not test_mode:
        raise ValueError("自定义 Research Provider 仅允许显式测试模式")
    resolved = settings or S7IntegrationSettings.from_env_file(env_file)
    local_execution_logger = None if test_mode else LocalExecutionLogger()
    execution_logger = local_execution_logger or NoopDiagnosticRecorder()
    model_names = {
        ModelTier.FAST: _secret(resolved, "deepseek_fast_model"),
        ModelTier.BALANCED: _secret(resolved, "deepseek_balanced_model"),
        ModelTier.STRONG: _secret(resolved, "deepseek_strong_model"),
    }
    owns_client = provider is None and http_client is None
    client = http_client
    if provider is None:
        client = client or httpx.AsyncClient()
        base_url = _secret(resolved, "deepseek_base_url")
        api_key = _secret(resolved, "deepseek_api_key")

    provider_registry = ModelProviderRegistry()
    candidates: list[ModelCandidate] = []
    for tier, model in model_names.items():
        provider_id = f"deepseek_{tier.value}"
        current = provider
        if current is None:
            current = DeepSeekStreamingProvider(
                client,
                model,
                api_key=api_key,
                base_url=base_url,
                timeout_ms=_OPERATION_MODEL_TIMEOUT_MS,
                diagnostic_recorder=execution_logger,
            )
        provider_registry.register(provider_id, current)
        candidates.append(_candidate(provider_id, provider_id, model, tier))

    cancellation = InMemoryCancellationSignal()
    model_cancellation = _RunScopedModelCancellation(cancellation)
    model_runtime = ModelRuntime(
        ModelPolicyRouter(candidates),
        provider_registry,
        cancellation_signal=model_cancellation,
        diagnostic_recorder=execution_logger,
    )
    if local_execution_logger is not None:
        local_execution_logger.log_capability("deepseek_chat", enabled=True)
    budget = ExecutionBudget(40, 10, 64_000, 32_000, 300_000, 1_000_000)
    research_client = None
    research_enabled = resolved.gates.get(
        IntegrationGate.DEEPSEEK_WEB_SEARCH.value, False
    )
    research_reason_code: str | None = None
    if not research_enabled:
        research_provider = None
        research_reason_code = "RESEARCH_GATE_DISABLED"
    if research_provider is None and research_enabled:
        from openai import AsyncOpenAI

        research_client = AsyncOpenAI(
            api_key=_secret(resolved, "deepseek_api_key"),
            base_url=_secret(resolved, "deepseek_base_url"),
            max_retries=0,
        )
        research_provider = DeepSeekWebSearchProvider(
            research_client,
            model=model_names[ModelTier.BALANCED],
            recorder=execution_logger,
        )
    if research_provider is None and research_reason_code is None:
        research_reason_code = "RESEARCH_PROVIDER_NOT_CONFIGURED"
    if local_execution_logger is not None:
        local_execution_logger.log_capability(
            "deepseek_web_search",
            enabled=research_provider is not None,
            reason_code=research_reason_code,
        )
    operation_agent = build_operation_agent(
        model_runtime,
        budget=budget,
        cancellation=cancellation,
        research_provider=research_provider,
        diagnostic_recorder=execution_logger,
        research_unavailable_code=(
            research_reason_code or "RESEARCH_PROVIDER_NOT_CONFIGURED"
        ),
    )
    submissions = ConversationSubmissionStore()
    direct_submissions = DirectConversationSubmissionStore()
    event_hub = EventHub()
    runtime_service: AgentRuntimeService | None = None

    async def publish_conversation_delta(run_id: str, delta: str) -> None:
        """把 Graph 的已治理正文交给唯一 Harness 决定是否仍可发布。"""
        if runtime_service is None:
            raise RuntimeError("本地 Harness 尚未完成装配")
        await runtime_service.publish_assistant_delta(run_id, delta)

    registry = GraphRegistry()
    registry.register(
        build_conversation_direct_registration(
            GeneralConversationAgent(model_runtime),
            direct_submissions.resolve,
            model_call_scope=model_cancellation.bind,
            output_publisher=publish_conversation_delta,
        )
    )
    registry.register(
        build_operation_multi_agent_registration(operation_agent, submissions.resolve)
    )
    clock = _SystemClock()
    graph_runtime = GraphRuntime(
        registry,
        cancellation_signal=cancellation,
        clock=clock,
        diagnostic_recorder=execution_logger,
    )
    runtime = AgentRuntimeService(
        repository=InMemoryRunRepository(),
        event_store=InMemoryRunEventStore(),
        router=StrategyRouter(registry.available_modes()),
        graph_runtime=graph_runtime,
        budget_guard=BudgetGuard(),
        budget=budget,
        clock=clock,
        id_generator=_UuidGenerator(),
        cancellation_signal=cancellation,
        event_hub=event_hub,
        diagnostic_recorder=execution_logger,
    )
    runtime_service = runtime
    if local_execution_logger is not None:
        runtime.add_run_event_listener(local_execution_logger.on_run_event)
        runtime.add_run_state_listener(local_execution_logger.on_run_state)
    conversation = ConversationService(
        runtime=runtime,
        # 真实模型结构化意图首包存在波动，组合根在 Run 总预算内给意图阶段 60 秒。
        interpreter=IntentInterpreter(model_runtime, timeout_ms=60_000),
        resolver=ScenarioResolver(),
        submissions=submissions,
        direct_submissions=direct_submissions,
    )
    app = create_app(
        runtime,
        event_hub=event_hub,
        conversation_service=conversation,
    )
    app.state.local_test_mode = test_mode
    return LocalAgentApplication(
        app,
        runtime,
        conversation,
        event_hub,
        client if owns_client else None,
        research_client,
    )


build_local_real_app = build_local_agent_application


__all__ = [
    "LocalAgentApplication",
    "build_local_agent_application",
    "build_local_real_app",
]
