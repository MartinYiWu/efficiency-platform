from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.orchestration.state import AgentGraphState

from .direct import _fact, _maybe_call, _Program


class WorkflowGraphBuilder:
    graph_id = "workflow"

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

        async def render_draft_prompt(state):
            return {**_fact(state, "prompt_rendered"), "prompt_id": "s2.workflow.draft"}

        async def call_draft_model(state):
            await _maybe_call(self.model_runtime, ("complete", "call_model"), state)
            return {
                **_fact(state, "model_completed"),
                "model_attempts": list(state.get("model_attempts", []))
                + [{"phase": "draft"}],
            }

        async def invoke_synthetic_lookup(state):
            result = await _maybe_call(self.tool_runtime, ("invoke", "lookup"), state)
            return {
                **_fact(state, "tool_completed"),
                "tool_output": getattr(result, "output", result)
                if result is not None
                else {"lookup": "synthetic-result"},
            }

        async def render_review_prompt(state):
            return {
                **_fact(state, "prompt_rendered"),
                "prompt_id": "s2.workflow.review",
            }

        async def call_review_model(state):
            await _maybe_call(self.model_runtime, ("complete", "call_model"), state)
            return {
                **_fact(state, "model_completed"),
                "model_attempts": list(state.get("model_attempts", []))
                + [{"phase": "review"}],
                "output": state.get("output")
                if isinstance(state.get("output"), JsonObject)
                else JsonObject((("content", state.get("input_text", "")),)),
            }

        async def validate_output(state):
            out = state.get("output")
            valid = isinstance(out, JsonObject) and any(
                k == "content" and isinstance(v, str) and v.strip()
                for k, v in out.items
            )
            return {
                **_fact(state, "output_validated"),
                "error_code": None if valid else "OUTPUT_SCHEMA_INVALID",
            }

        for name, fn in (
            ("build_context", build_context),
            ("render_draft_prompt", render_draft_prompt),
            ("call_draft_model", call_draft_model),
            ("invoke_synthetic_lookup", invoke_synthetic_lookup),
            ("render_review_prompt", render_review_prompt),
            ("call_review_model", call_review_model),
            ("validate_output", validate_output),
        ):
            graph.add_node(name, fn)
        graph.add_edge(START, "build_context")
        graph.add_edge("build_context", "render_draft_prompt")
        graph.add_edge("render_draft_prompt", "call_draft_model")
        graph.add_edge("call_draft_model", "invoke_synthetic_lookup")
        graph.add_edge("invoke_synthetic_lookup", "render_review_prompt")
        graph.add_edge("render_review_prompt", "call_review_model")
        graph.add_edge("call_review_model", "validate_output")
        graph.add_edge("validate_output", END)
        return _Program(
            graph.compile(checkpointer=self.checkpointer),
            self.model_runtime,
            self.context_builder,
            self.tool_runtime,
        )
