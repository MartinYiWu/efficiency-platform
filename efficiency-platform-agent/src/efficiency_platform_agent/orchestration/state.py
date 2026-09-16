"""S2 LangGraph 程序传递的、仅含 JSON 数据的类型化状态。"""

from __future__ import annotations

from typing import TypedDict

from efficiency_platform_agent.core.run import JsonObject, JsonValue


class AgentGraphState(TypedDict, total=True):
    run_id: str
    tenant_id: str
    user_id: str
    request_id: str
    input_text: str
    strategy: str
    workflow_id: str | None
    strategy_payload_schema_version: str
    strategy_payload: JsonObject
    allowed_tools: list[str]
    estimated_input_tokens: int
    prompt_id: str | None
    tool_output: JsonValue
    model_attempts: list[dict[str, JsonValue]]
    runtime_facts: list[dict[str, JsonValue]]
    usage: dict[str, JsonValue]
    budget_state: dict[str, JsonValue]
    output: JsonValue
    error_code: str | None
    degraded: bool
    test_mode: str | None
    next_status: str | None
