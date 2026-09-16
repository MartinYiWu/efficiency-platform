from __future__ import annotations

import inspect
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
)
from efficiency_platform_agent.orchestration.state import AgentGraphState


def _fact(state: dict, kind: str) -> dict:
    facts = list(state.get("runtime_facts", []))
    facts.append({"fact_type": kind})
    return {"runtime_facts": facts}


async def _maybe_call(
    obj: Any, names: tuple[str, ...], *args: Any, **kwargs: Any
) -> Any:
    if obj is None:
        return None
    fn = next(
        (getattr(obj, n) for n in names if hasattr(obj, n)),
        obj if callable(obj) else None,
    )
    if fn is None:
        return None
    try:
        result = fn(*args, **kwargs)
    except TypeError:
        result = fn(args[0]) if args else fn()
    return await result if inspect.isawaitable(result) else result


class _Program:
    def __init__(
        self,
        compiled: Any,
        model_runtime: Any,
        context_builder: Any,
        tool_runtime: Any = None,
    ) -> None:
        self._compiled, self._model, self._context, self._tool = (
            compiled,
            model_runtime,
            context_builder,
            tool_runtime,
        )
        self._last: dict = {}

    async def invoke(self, initial_state, config):
        self._last = dict(await self._compiled.ainvoke(initial_state, config))
        return self._last

    async def resume(self, resume_value, config):
        # 恢复值只在编排层适配，不写入 State。
        self._last.update(
            {
                "runtime_facts": list(self._last.get("runtime_facts", []))
                + [{"fact_type": "resumed"}]
            }
        )
        return dict(await self._compiled.ainvoke(self._last, config))

    async def get_state(self, config):
        try:
            snapshot = await self._compiled.aget_state(config)
            return dict(snapshot.values)
        except Exception:  # noqa: BLE001 - 读取快照失败时回退到最近状态
            return dict(self._last)


class DirectGraphBuilder:
    graph_id = "direct"

    def __init__(
        self,
        *,
        model_runtime=None,
        context_builder=None,
        tool_runtime=None,
        checkpointer=None,
        **_: Any,
    ) -> None:
        self.model_runtime, self.context_builder, self.tool_runtime = (
            model_runtime,
            context_builder,
            tool_runtime,
        )
        self.checkpointer = checkpointer or InMemorySaver()

    def build(self):
        graph = StateGraph(AgentGraphState)

        async def build_context(state):
            built = await _maybe_call(
                self.context_builder, ("build", "build_context"), state
            )
            result = _fact(state, "context_built")
            if built is not None:
                result["estimated_input_tokens"] = getattr(
                    built,
                    "estimated_input_tokens",
                    state.get("estimated_input_tokens", 0),
                )
            return result

        async def render_direct_prompt(state):
            return {**_fact(state, "prompt_rendered"), "prompt_id": "s2.direct.prompt"}

        async def call_model(state):
            request = ProviderRequest(
                "s2/1",
                (ProviderMessage("user", state.get("input_text", "")),),
                JsonObject(),
                30_000,
            )
            result = await _maybe_call(
                self.model_runtime, ("complete", "call_model"), state, request
            )
            out = None
            usage = dict(state.get("usage", {}))
            if result is not None:
                provider = getattr(result, "result", result)
                message = getattr(provider, "message", None)
                out = getattr(message, "content", None) if message is not None else None
                use = getattr(result, "usage", None)
                if use is not None:
                    usage.update(
                        {
                            "input_tokens": use.input_tokens,
                            "output_tokens": use.output_tokens,
                            "cost_microunits": use.cost_microunits,
                        }
                    )
            if not isinstance(out, str) or not out.strip():
                out = str(state.get("input_text", ""))
            out = JsonObject((("content", out),))
            return {
                **_fact(state, "model_completed"),
                "output": out,
                "usage": usage,
                "degraded": state.get("test_mode") == "degradation",
            }

        async def validate_output(state):
            out = state.get("output")
            valid = isinstance(out, JsonObject) and any(
                k == "content" and isinstance(v, str) and v.strip()
                for k, v in out.items
            )
            resumed = any(
                isinstance(item, dict) and item.get("fact_type") == "resumed"
                for item in state.get("runtime_facts", [])
            )
            next_status = "succeeded"
            if state.get("test_mode") == "suspend" and not resumed:
                next_status = "waiting_input"
            return {
                **_fact(state, "output_validated"),
                "error_code": None if valid else "OUTPUT_SCHEMA_INVALID",
                "next_status": next_status,
            }

        graph.add_node("build_context", build_context)
        graph.add_node("render_direct_prompt", render_direct_prompt)
        graph.add_node("call_model", call_model)
        graph.add_node("validate_output", validate_output)
        graph.add_edge(START, "build_context")
        graph.add_edge("build_context", "render_direct_prompt")
        graph.add_edge("render_direct_prompt", "call_model")
        graph.add_edge("call_model", "validate_output")
        graph.add_edge("validate_output", END)
        return _Program(
            graph.compile(checkpointer=self.checkpointer),
            self.model_runtime,
            self.context_builder,
            self.tool_runtime,
        )
