"""Stable execution enums independent of orchestration frameworks."""

from enum import StrEnum


class RunStatus(StrEnum):
    """Complete lifecycle of an Agent run."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class StrategyMode(StrEnum):
    """Execution modes selected by the strategy router."""

    DIRECT = "direct"
    WORKFLOW = "workflow"
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    MULTI_AGENT = "multi_agent"


class AgentKind(StrEnum):
    """Agent 在受控多 Agent 拓扑中的稳定角色。"""

    SUPERVISOR = "supervisor"
    SPECIALIST = "specialist"
