"""Framework-neutral extension ports for strategies, Agents, tools, and models."""

from collections.abc import AsyncIterator, Awaitable
from typing import Protocol, runtime_checkable

from .agent import AgentSpec
from .run import (
    ExtensionDescriptor,
    ProviderRequest,
    ProviderResult,
    ProviderStreamChunk,
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
    """未来 Specialist Agent 或 Agent 子图的稳定扩展端口。"""

    descriptor: ExtensionDescriptor
    spec: AgentSpec

    async def run(self, task: SupervisorTask) -> RunResult:
        """只执行 Supervisor 分配且已裁剪上下文的子任务。"""
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


@runtime_checkable
class StreamingModelProvider(Protocol):
    """附加流式模型端口，不改变基础 ModelProvider 契约。"""

    def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamChunk]:
        """返回增量事件；消费者负责在中断时关闭异步迭代器。"""
        ...


@runtime_checkable
class CancellationSignal(Protocol):
    """模型或工具调用可查询的取消信号。"""

    def wait_requested(self) -> bool | Awaitable[bool]:
        """返回是否已经请求取消。"""
        ...
