"""从服务端运行绑定与显式发布资产解析最终发送计划。"""

from collections.abc import Mapping
from dataclasses import replace
from time import time

from efficiency_platform_agent.context.dispatch import DispatchPlan
from efficiency_platform_agent.context.policy import ContextPiece, ContextPolicy
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    ContextOperation,
)
from efficiency_platform_agent.core.execution_control import (
    current_operation_key,
    current_run_control,
)
from efficiency_platform_agent.core.memory import ExecutionScope
from efficiency_platform_agent.core.memory_execution import MemoryExecutionStore
from efficiency_platform_agent.core.run import ProviderMessage, ProviderRequest
from efficiency_platform_agent.core.run_context_binding import current_run_context
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.memory.packet_reader import PacketMemoryReader


class ServerDispatchAuthority:
    def __init__(
        self,
        published: Mapping[
            tuple[str, str, str], ContextMetadata | tuple[ContextMetadata, ...]
        ],
        execution_agents: Mapping[str, tuple[str, str]] | None = None,
        *,
        memory_execution_store: MemoryExecutionStore | None = None,
    ):
        self._published = {
            key: value if isinstance(value, tuple) else (value,)
            for key, value in published.items()
        }
        self._execution_agents = dict(execution_agents or {})
        self.memory_execution_store = memory_execution_store

    @staticmethod
    def _validate_limits(metadata: ContextMetadata) -> None:
        capacity, limits = metadata.capacity, metadata.limits
        options = dict(metadata.options.items)
        outputs = [
            options[key]
            for key in ("max_tokens", "max_completion_tokens")
            if key in options
        ]
        if (
            limits.context_window_tokens != capacity.context_window_tokens
            or limits.independent_input_limit != capacity.max_input_tokens
            or limits.output_reserve_tokens > capacity.max_output_tokens
            or any(
                type(value) is not int
                or value <= 0
                or value > limits.output_reserve_tokens
                for value in outputs
            )
            or (
                not outputs
                and limits.output_reserve_tokens != capacity.max_output_tokens
            )
        ):
            raise ValueError("CONTEXT_CAPACITY_LIMITS_MISMATCH")

    def assert_ready(self) -> None:
        if not self._published or not self._execution_agents:
            raise ValueError("CONTEXT_PUBLISHED_ASSETS_REQUIRED")
        for (provider, model, node), variants in self._published.items():
            if not variants:
                raise ValueError("CONTEXT_PUBLISHED_ASSETS_INVALID")
            original = variants[0]
            for metadata in variants:
                self._validate_limits(metadata)
                if (
                    metadata.policy_version != original.policy_version
                    or metadata.capacity != original.capacity
                ):
                    raise ValueError("CONTEXT_PUBLISHED_BUNDLE_MISMATCH")
                if (
                    not metadata.capacity.verified
                    or (metadata.capacity.provider, metadata.capacity.model)
                    != (provider, model)
                    or node not in self._execution_agents
                ):
                    raise ValueError("CONTEXT_PUBLISHED_ASSETS_INVALID")

    @staticmethod
    def _matches_options(metadata: ContextMetadata, request: ProviderRequest) -> bool:
        published, actual = dict(metadata.options.items), dict(request.options.items)
        if set(published) != set(actual):
            return False
        for key, value in actual.items():
            if key in ("max_tokens", "max_completion_tokens"):
                upper = published[key]
                if (
                    type(value) is not int
                    or type(upper) is not int
                    or not 0 < value <= upper
                ):
                    return False
            elif value != published[key]:
                return False
        return True

    async def resolve(
        self, request: ProviderRequest, provider_id: str, model: str
    ) -> DispatchPlan:
        binding = current_run_context()
        if binding is None:
            raise ValueError("CONTEXT_RUN_BINDING_REQUIRED")
        stage = current_model_stage()
        stage_id = stage.stage_id if stage is not None else current_operation_key()
        node_id = getattr(stage, "node_id", None) if stage is not None else stage_id
        variants = self._published.get((provider_id, model, node_id or ""))
        if not variants or any(not metadata.capacity.verified for metadata in variants):
            raise ValueError("CONTEXT_CAPACITY_NOT_PUBLISHED")
        if any(
            metadata.policy_version != variants[0].policy_version
            or metadata.capacity != variants[0].capacity
            for metadata in variants
        ):
            raise ValueError("CONTEXT_PUBLISHED_BUNDLE_MISMATCH")
        for candidate in variants:
            self._validate_limits(candidate)
        metadata = next(
            (item for item in variants if self._matches_options(item, request)), None
        )
        if metadata is None:
            raise ValueError("CONTEXT_PUBLISHED_OPTIONS_MISMATCH")
        metadata = replace(metadata, options=request.options)
        self._validate_limits(metadata)
        if not stage_id:
            raise ValueError("CONTEXT_STAGE_REQUIRED")
        if time() >= binding.deadline_epoch_seconds:
            raise ValueError("CONTEXT_DEADLINE_EXPIRED")
        control = current_run_control()
        if control is not None:
            control.check()
        if (metadata.capacity.provider, metadata.capacity.model) != (
            provider_id,
            model,
        ):
            raise ValueError("CONTEXT_PROVIDER_BINDING_MISMATCH")
        authorization = self._execution_agents.get(node_id or "")
        if authorization is None:
            raise ValueError("CONTEXT_EXECUTION_AGENT_NOT_PUBLISHED")
        execution_agent_id, purpose = authorization
        scope = ExecutionScope(
            binding.conversation,
            binding.task_id,
            binding.execution_id,
            (stage.subtask_id if stage is not None else None) or metadata.node_id,
            purpose,
            execution_agent_id,
        )
        policy = ContextPolicy(metadata.node_id, metadata.policy_version, scope)
        # 已有入口的完整消息组全部必保；不推断或新增历史/记忆读取权限。
        pieces: tuple[ContextPiece, ...] = (
            ContextPiece(
                "final-request",
                scope,
                request.messages,
                required=True,
                kind="current_request",
            ),
        )
        operation = ContextOperation(stage_id, 1, binding.deadline_epoch_seconds, True)
        if binding.memory_context is not None:
            if self.memory_execution_store is None:
                raise ValueError("MEMORY_AUTHORITY_REQUIRED")
            context = binding.memory_context
            if binding.conversation.domain == "customer-service" and node_id not in {
                "customer-service:intent",
                "customer-service:answer_general",
            }:
                raise ValueError("MEMORY_KNOWLEDGE_LINEAGE_ADAPTER_REQUIRED")
            if binding.conversation.domain == "operations" and node_id not in {
                "intent",
                "direct",
            }:
                raise ValueError("MEMORY_EXPERT_LINEAGE_ADAPTER_REQUIRED")
            if any(
                message.role == "tool" or message.tool_calls
                for message in request.messages
            ):
                raise ValueError("MEMORY_TOOL_LINEAGE_REQUIRED")
            packet = context.packet
            operation = replace(operation, memory_disabled=False)
            live_validator = StoredMemoryPacketValidator(self.memory_execution_store)
            validator = await live_validator.validator(scope)
            selection = await PacketMemoryReader(validator).read(
                scope,
                packet,
                context.policy.field_allowlist
                if purpose == "assistant_response"
                else frozenset(),
                operation,
            )
            input_dependencies = context.input_dependencies
            if not input_dependencies:
                raise ValueError("MEMORY_CURRENT_INPUT_DEPENDENCIES_REQUIRED")
            pieces = (replace(pieces[0], safety_dependencies=input_dependencies),)
            for item in selection.items:
                message = ProviderMessage(
                    "user",
                    "已确认的响应展示偏好（仅影响语言、详略或格式，不改变任务事实、规则、评分和判断）："
                    + item.field_key
                    + "="
                    + item.value,
                )
                pieces += (
                    ContextPiece(
                        "memory-" + item.item_id,
                        scope,
                        (message,),
                        item.safety_dependencies,
                        kind="memory",
                    ),
                )
            policy = replace(policy, authorized_dependencies=packet.safety_dependencies)
            final_request = replace(
                request,
                messages=tuple(
                    message for piece in pieces for message in piece.messages
                ),
            )
            return DispatchPlan(
                scope, policy, pieces, metadata, operation, packet, final_request
            )
        return DispatchPlan(scope, policy, pieces, metadata, operation)
