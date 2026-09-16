"""将通用对话注册到 S2 唯一 DIRECT Graph Runtime。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from efficiency_platform_agent.agents.conversation.general_agent import (
    GeneralConversationAgent,
    GeneralConversationError,
)
from efficiency_platform_agent.contracts.direct_conversation import (
    DirectConversationSubmission,
)
from efficiency_platform_agent.conversation.direct_submission import (
    DirectConversationSubmissionError,
)
from efficiency_platform_agent.core.budget import BudgetCharge, BudgetState
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import JsonObject, JsonValue, RunRequest
from efficiency_platform_agent.orchestration.contracts import GraphRegistration
from efficiency_platform_agent.orchestration.state import AgentGraphState

DirectSubmissionResolver = Callable[
    [RunRequest, Mapping[str, object]], Awaitable[DirectConversationSubmission]
]
ModelCallScope = Callable[[str], AbstractContextManager[None]]
ConversationOutputPublisher = Callable[[str, str], Awaitable[None]]


class _EmptyPayloadAdapter:
    """声明通用对话不接收任何策略 payload 字段。"""

    def adapt(self, schema_version: str, payload: JsonObject) -> JsonObject:
        if schema_version != "strategy.none/1" or payload.items:
            raise ValueError("DIRECT_CONVERSATION_PAYLOAD_FORBIDDEN")
        return payload


class _ConversationDirectProgram:
    """把 LangGraph 编译对象适配为 S2 GraphProgram。"""

    def __init__(self, compiled: Any) -> None:
        self._compiled = compiled
        self._last: dict[str, Any] = {}

    async def invoke(
        self, initial_state: AgentGraphState, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        """执行单节点通用对话；副作用仅为一次模型调用或本地响应。"""
        self._last = dict(await self._compiled.ainvoke(initial_state, config))
        # LangGraph 内保留 JSON；返回统一 Runtime 前归一化为原 Run 的预算值对象。
        raw_budget = self._last.get("budget_state")
        if isinstance(raw_budget, Mapping):
            consumed = dict(raw_budget["consumed"])
            usage = self._last.get("usage", {})
            consumed["iterations"] += len(self._last.get("model_attempts", []))
            for key in ("input_tokens", "output_tokens", "cost_microunits"):
                consumed[key] += usage.get(key, 0)
            self._last["budget_state"] = BudgetState(
                BudgetCharge(**consumed),
                raw_budget["started_at_epoch_ms"],
                raw_budget["deadline_epoch_ms"],
            )
        return self._last

    async def resume(
        self, resume_value: JsonObject, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        """DIRECT 对话没有暂停点，任何恢复尝试都失败关闭。"""
        del resume_value, config
        raise ValueError("DIRECT_CONVERSATION_RESUME_UNSUPPORTED")

    async def get_state(
        self, config: Mapping[str, JsonValue]
    ) -> Mapping[str, JsonValue]:
        """返回检查点可见状态；读取失败时退回最近一次不可变快照。"""
        try:
            snapshot = await self._compiled.aget_state(config)
            return dict(snapshot.values)
        except Exception:  # noqa: BLE001 - 只读检查点失败不泄露框架异常
            return dict(self._last)


class ConversationDirectGraphBuilder:
    """构建一个无工具、无交付物的通用对话单节点 Graph。"""

    def __init__(
        self,
        agent: GeneralConversationAgent,
        resolver: DirectSubmissionResolver,
        model_call_scope: ModelCallScope | None = None,
        output_publisher: ConversationOutputPublisher | None = None,
    ) -> None:
        if not isinstance(agent, GeneralConversationAgent):
            raise TypeError("agent必须是GeneralConversationAgent")
        if not callable(resolver):
            raise TypeError("resolver必须可调用")
        self.agent = agent
        self.resolver = resolver
        self.model_call_scope = model_call_scope or (lambda _run_id: nullcontext())
        self.output_publisher = output_publisher
        self.checkpointer = InMemorySaver()

    def build(self) -> _ConversationDirectProgram:
        """构建通用对话 Graph；提交消费和模型调用只发生一次。"""
        graph = StateGraph(AgentGraphState)

        async def execute(state: AgentGraphState) -> dict[str, Any]:
            """校验身份并返回最小状态增量；异常只写稳定错误码。"""
            try:
                request = RunRequest(
                    str(state.get("request_id", "")),
                    str(state.get("tenant_id", "")),
                    str(state.get("user_id", "")),
                    str(state.get("input_text", "")),
                )
                submission = await self.resolver(request, state)
            except DirectConversationSubmissionError as error:
                return {
                    "next_status": RunStatus.FAILED.value,
                    "error_code": error.code,
                    "output": None,
                }
            except (TypeError, ValueError):
                return {
                    "next_status": RunStatus.FAILED.value,
                    "error_code": "DIRECT_CONVERSATION_SUBMISSION_INVALID",
                    "output": None,
                }
            if (
                submission.request.tenant_id != state.get("tenant_id")
                or submission.request.user_id != state.get("user_id")
                or submission.request.request_id != state.get("request_id")
                or submission.current_message != state.get("input_text")
            ):
                return {
                    "next_status": RunStatus.FAILED.value,
                    "error_code": "DIRECT_CONVERSATION_IDENTITY_MISMATCH",
                    "output": None,
                }
            if submission.local_response is not None:
                return {
                    "next_status": RunStatus.SUCCEEDED.value,
                    "output": {"content": submission.local_response},
                    "usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_microunits": 0,
                        "estimated": False,
                    },
                    "degraded": False,
                }
            try:
                with self.model_call_scope(str(state.get("run_id", ""))):
                    output_publisher = self.output_publisher
                    if output_publisher is None:
                        result = await self.agent.execute(submission)
                    else:
                        run_id = str(state.get("run_id", ""))

                        async def publish(delta: str) -> None:
                            """将 Agent 已治理的正文交给当前 Run 的窄输出端口。"""
                            await output_publisher(run_id, delta)

                        result = await self.agent.execute(submission, on_delta=publish)
            except GeneralConversationError as error:
                return {
                    "next_status": RunStatus.FAILED.value,
                    "error_code": error.code,
                    "output": None,
                    "usage": {
                        "input_tokens": error.usage.input_tokens,
                        "output_tokens": error.usage.output_tokens,
                        "cost_microunits": error.usage.cost_microunits,
                        "estimated": error.usage.estimated,
                    },
                    "degraded": error.degraded,
                    "model_attempts": [
                        {"attempt": item.attempt} for item in error.attempts
                    ],
                }
            return {
                "next_status": RunStatus.SUCCEEDED.value,
                "output": {"content": result.content},
                "usage": {
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cost_microunits": result.usage.cost_microunits,
                    "estimated": result.usage.estimated,
                },
                "degraded": result.degraded,
                "model_attempts": [
                    {"attempt": item.attempt} for item in result.attempts
                ],
            }

        graph.add_node("general_conversation", execute)
        graph.set_entry_point("general_conversation")
        graph.add_edge("general_conversation", END)
        return _ConversationDirectProgram(graph.compile(checkpointer=self.checkpointer))


def build_conversation_direct_registration(
    agent: GeneralConversationAgent,
    resolver: DirectSubmissionResolver,
    *,
    model_call_scope: ModelCallScope | None = None,
    output_publisher: ConversationOutputPublisher | None = None,
) -> GraphRegistration:
    """显式登记通用对话 DIRECT Graph，不改变 S2 公共生命周期。"""
    return GraphRegistration(
        graph_id="general-conversation",
        strategy=StrategyMode.DIRECT,
        graph_version="1.0.0",
        checkpoint_ns="s2:direct:1",
        strategy_payload_schema_version="strategy.none/1",
        allowed_strategy_payload_keys=frozenset(),
        allowed_next_statuses=frozenset(
            {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
        ),
        builder=ConversationDirectGraphBuilder(
            agent, resolver, model_call_scope, output_publisher
        ),
        payload_adapter=_EmptyPayloadAdapter(),
    )


__all__ = [
    "ConversationDirectGraphBuilder",
    "DirectSubmissionResolver",
    "build_conversation_direct_registration",
]
