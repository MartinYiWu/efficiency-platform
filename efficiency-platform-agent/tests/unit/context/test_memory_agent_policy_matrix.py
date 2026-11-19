"""离线完整Authority→Controller→FakeProvider入口矩阵；不连接数据库或付费端点。"""

from dataclasses import replace
from hashlib import sha256
from time import time
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.context.specialist_lineage import register_task_slice
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.context_dispatch import model_stage
from efficiency_platform_agent.core.context_ports import (
    ContextMetadata,
    OperationReceipt,
)
from efficiency_platform_agent.core.memory import (
    ConversationScope,
    MemoryContextPacket,
    MemoryPolicy,
    MemoryReference,
    SourceDependency,
)
from efficiency_platform_agent.core.memory_execution import (
    MemoryExecutionContext,
    MemoryExecutionGrant,
    MemoryExecutionRecord,
)
from efficiency_platform_agent.core.memory_lineage import (
    current_specialist_registry,
    registered_specialist_input,
    specialist_lineage_session,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
    SupervisorTask,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)

EXPERTS = (
    "operation.research.insight",
    "operation.channel.content",
    "operation.ip.strategy",
    "operation.quality.review",
    "operation.campaign.plan",
    "operation.user_growth.plan",
    "operation.brand.strategy",
    "operation.product.plan",
    "operation.analytics.review",
    "operation.community.plan",
    "operation.content.create",
)


class TechnicalAuthority:
    def __init__(self, record):
        self.record = record

    async def get(self, tenant, execution):
        return self.record if (tenant, execution) == ("tenant", "execution") else None


class TechnicalManifest:
    def __init__(self):
        self.manifests = []
        self.receipts = {}

    async def save_manifest_once(self, manifest, operation):
        self.manifests.append(manifest)
        self.receipts[operation.operation_id] = OperationReceipt(
            manifest.canonical_request_hmac,
            "NOT_SENT",
            operation.deadline_epoch_seconds,
        )
        return manifest

    async def get_operation_receipt(self, scope, operation_id):
        return self.receipts.get(operation_id)

    async def mark_sending(self, manifest, operation):
        return True

    async def record_receipt(self, manifest, status, receipt_ref=None):
        return True


class Counter:
    def measure(self, request, capacity):
        count = (
            sum(len(str(message.content).encode()) for message in request.messages)
            + len(str(request.options))
            + 256
        )
        return TokenMeasurement(count, (("full", count),), "offline-fake", True)


class FakeProvider:
    descriptor = SimpleNamespace(name="fake")

    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResult(
            "provider-result/1",
            ProviderMessage("assistant", "合成回答"),
            ProviderUsage(1, 1, 0, 0, 0),
        )


def setup(agent, *, specialist=False, hr=False, publication=True, knowledge=False):
    now = int(time())
    domain = (
        "hr"
        if hr
        else "customer-service"
        if agent == "customer-service"
        else "operations"
    )
    conversation = ConversationScope(
        "tenant",
        "user",
        domain,
        domain,
        "TASK_ONLY" if hr else "CONVERSATION",
        None if hr else "session",
    )
    node = (
        agent
        if hr
        else "operation-specialist:" + agent
        if specialist
        else "customer-service:answer_general"
        if domain == "customer-service"
        else "direct"
    )
    if knowledge:
        node = "customer-service:answer_company"
    purpose = "evaluate" if hr else "assistant_response"
    current = SourceDependency(
        "CURRENT_USER_MESSAGE", "current", sha256("目标".encode()).hexdigest(), 0, 1, 0
    )
    history = SourceDependency(
        "CURRENT_USER_MESSAGE",
        "old",
        sha256("父历史私有正文".encode()).hexdigest(),
        0,
        1,
        0,
    )
    unused = SourceDependency(
        "CURRENT_USER_MESSAGE",
        "unused-authorized",
        sha256("未见授权数据".encode()).hexdigest(),
        0,
        1,
        0,
    )
    packet = MemoryContextPacket(
        "packet",
        1,
        conversation,
        "task",
        "execution",
        "memory/1",
        1,
        now,
        now + 50,
        0,
        0,
        0,
        "semantic",
        "parent",
        (),
        (current, history, unused),
    )
    policy = MemoryPolicy(
        "memory",
        "memory/1",
        domain,
        frozenset({domain, agent}),
        readable_layers=frozenset({"semantic"}),
        allowed_scopes=frozenset({"USER_PRIVATE"}),
        source_types=frozenset({"CURRENT_USER_MESSAGE"}),
    )
    context = MemoryExecutionContext(
        packet,
        policy,
        (MemoryExecutionGrant(node, agent, purpose),),
        now + 90,
        memory_packet_digest(packet),
        memory_packet_semantic_digest(packet),
        "a" * 64,
        (current, history),
    )
    authority = TechnicalAuthority(
        MemoryExecutionRecord(
            context, "runtime", "OPERATIONS", "a" * 64, now + 80, "ACTIVE", 1, 0, 0, 0
        )
    )
    capacity = ModelCapacity(
        "fake",
        "fake",
        "1",
        5000,
        None,
        100,
        "fake/1",
        "fake/1",
        "none",
        True,
        "offline",
    )
    metadata = ContextMetadata(
        node,
        "window/1",
        "prompt/1",
        "tool/1",
        "schema/1",
        0,
        capacity,
        WindowLimits(5000, None, 100, 0, 4900),
        JsonObject(),
    )
    manifests = TechnicalManifest()
    controller = ContextController(
        Counter(),
        manifests,
        b"k" * 32,
        validator=StoredMemoryPacketValidator(authority),
    )
    dispatch = ContextDispatch(
        controller,
        manifests,
        ServerDispatchAuthority(
            {("fake", "fake", node): metadata},
            {node: (agent, purpose)},
            memory_execution_store=authority,
            specialist_lineage_enabled=publication,
        ),
    )
    model = FakeProvider()
    provider = ControlledModelProvider(
        model, dispatch, "fake", "fake", paid_transport=False
    )
    binding = RunContextBinding(
        conversation, "task", "execution", now + 80, None if hr else context
    )
    task = SupervisorTask(
        "subtask",
        "execution",
        agent,
        JsonObject((("goal", "目标"),)),
        JsonObject(),
        frozenset(),
        ExecutionBudget(3, 0, 1000, 100, 30000, 0),
    )
    request = ProviderRequest(
        "provider-request/1", (ProviderMessage("user", "目标"),), JsonObject(), 1000
    )
    return node, task, request, current, history, provider, binding, manifests, model


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", EXPERTS)
async def test_eleven_registered_experts_send_only_actual_current_slice(agent):
    node, task, request, current, history, provider, binding, manifests, model = setup(
        agent, specialist=True
    )
    with bind_run_context(binding), specialist_lineage_session():
        register_task_slice(task, goal="目标", upstream=(), parent_plan_digest="b" * 64)
        with (
            registered_specialist_input(task),
            model_stage("operation", b"frozen", node_id=node, subtask_id=task.task_id),
        ):
            await provider.complete(request)
        with (
            pytest.raises(ValueError, match="NOT_REGISTERED"),
            registered_specialist_input(
                replace(task, input_data=JsonObject((("goal", "伪造父历史"),)))
            ),
        ):
            pass
    assert len(model.requests) == 1
    assert all(
        "父历史" not in str(message.content) for message in model.requests[0].messages
    )
    assert set(manifests.manifests[0].safety_dependencies) == {current, history}
    assert all(
        dependency.source_id != "unused-authorized"
        for dependency in manifests.manifests[0].safety_dependencies
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "agent,hr",
    [("operations", False), ("customer-service", False)]
    + [("hr:" + str(skill), True) for skill in range(6101, 6111)],
)
async def test_direct_csr_general_and_ten_hr_fact_only_stages(agent, hr):
    node, _, request, _, _, provider, binding, manifests, model = setup(agent, hr=hr)
    with bind_run_context(binding), model_stage("operation", b"frozen", node_id=node):
        await provider.complete(request)
    assert len(model.requests) == 1
    assert model.requests[0].messages == request.messages
    if hr:
        assert binding.conversation.session_id is None
        assert binding.memory_context is None
        assert not manifests.manifests[0].safety_dependencies


@pytest.mark.asyncio
async def test_unpublished_expert_and_knowledge_lineage_fail_before_provider():
    node, task, request, _, _, provider, binding, _, model = setup(
        EXPERTS[0], specialist=True, publication=False
    )
    with bind_run_context(binding), specialist_lineage_session():
        register_task_slice(task, goal="目标", upstream=(), parent_plan_digest="b" * 64)
        with (
            registered_specialist_input(task),
            model_stage("operation", b"frozen", node_id=node, subtask_id=task.task_id),
            pytest.raises(ValueError, match="LINEAGE_ADAPTER_REQUIRED"),
        ):
            await provider.complete(request)
    assert not model.requests
    node, _, request, _, _, provider, binding, _, model = setup(
        "customer-service", knowledge=True
    )
    with (
        bind_run_context(binding),
        model_stage("knowledge", b"frozen", node_id=node),
        pytest.raises(ValueError, match="KNOWLEDGE_LINEAGE_ADAPTER_REQUIRED"),
    ):
        await provider.complete(request)
    assert not model.requests


@pytest.mark.asyncio
async def test_upstream_inherits_actual_selected_preference_from_final_manifest():
    node, task, request, _, _, provider, binding, manifests, _ = setup(
        EXPERTS[0], specialist=True
    )
    context = binding.memory_context
    assert context is not None
    preference = SourceDependency(
        "USER_PREFERENCE_DECISION", "preference", "1", 0, 1, 0
    )
    packet = replace(
        context.packet,
        items=(
            MemoryReference(
                "preference-item", "1", "response.language", "zh-CN", (preference,)
            ),
        ),
        safety_dependencies=(*context.packet.safety_dependencies, preference),
    )
    policy = replace(
        context.policy,
        field_allowlist=frozenset({"response.language"}),
        source_types=context.policy.source_types | {"USER_PREFERENCE_DECISION"},
    )
    context = replace(
        context,
        packet=packet,
        policy=policy,
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    binding = replace(binding, memory_context=context)
    authority = provider.dispatch.authority.memory_execution_store
    authority.record = replace(authority.record, context=context)
    with bind_run_context(binding), specialist_lineage_session():
        register_task_slice(task, goal="目标", upstream=(), parent_plan_digest="b" * 64)
        with (
            registered_specialist_input(task),
            model_stage("operation", b"frozen", node_id=node, subtask_id=task.task_id),
        ):
            await provider.complete(request)
        registry = current_specialist_registry()
        assert registry is not None
        assert preference in registry.dependencies(task.task_id)
    assert preference in manifests.manifests[0].safety_dependencies
