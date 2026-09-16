"""Framework-neutral extension ports for strategies, Agents, tools, and models."""

from typing import Protocol, runtime_checkable

from .run import (
    ExtensionDescriptor,
    ProviderRequest,
    ProviderResult,
    RunContext,
    RunRequest,
    RunResult,
    SupervisorTask,
    ToolRequest,
    ToolResult,
)


@runtime_checkable
class StrategyExecutor(Protocol):
    """Executes one routed strategy within the unified runtime."""

    descriptor: ExtensionDescriptor

    async def execute(self, request: RunRequest, context: RunContext) -> RunResult:
        """Execute the request and return its normalized result."""
        ...


@runtime_checkable
class AgentPlugin(Protocol):
    """Extension point for a future specialist Agent or Agent subgraph."""

    descriptor: ExtensionDescriptor

    async def run(self, task: SupervisorTask) -> RunResult:
        """Run only the Supervisor-assigned, context-trimmed specialist task."""
        ...


@runtime_checkable
class Tool(Protocol):
    """Tool contract shared by internal, external, and MCP tools."""

    descriptor: ExtensionDescriptor

    async def invoke(
        self,
        request: ToolRequest,
        context: RunContext,
    ) -> ToolResult:
        """Invoke the Tool with a governed request and run context."""
        ...


@runtime_checkable
class ModelProvider(Protocol):
    """Model provider port kept independent from every vendor SDK."""

    descriptor: ExtensionDescriptor

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """Return a normalized message, usage, or structured error."""
        ...
