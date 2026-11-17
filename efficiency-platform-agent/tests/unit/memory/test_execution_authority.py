"""真实Controller/PacketReader/最终Provider链，Fake仅在模型与技术权威读取边界。"""

from dataclasses import replace
from time import time
from types import SimpleNamespace

import pytest

from efficiency_platform_agent.context.controller import ContextController
from efficiency_platform_agent.context.dispatch import (
    ContextDispatch,
    ControlledModelProvider,
)
from efficiency_platform_agent.core.context_control import ModelCapacity, WindowLimits
from efficiency_platform_agent.core.context_dispatch import model_stage
from efficiency_platform_agent.core.context_ports import ContextMetadata
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
from efficiency_platform_agent.core.run import (
    JsonObject,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.harness.context_authority import ServerDispatchAuthority
from efficiency_platform_agent.memory.execution_authority import (
    StoredMemoryPacketValidator,
)
from efficiency_platform_agent.persistence.context_manifest import (
    MySqlContextManifestStore,
)
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.unit.persistence.test_context_manifest import Counter, LocalEngine


class LocalAuthority:
    def __init__(self, record):
        self.record = record

    async def get(self, tenant, execution):
        return (
            self.record
            if (tenant, execution)
            == (
                self.record.context.packet.scope.tenant_id,
                self.record.context.packet.execution_id,
            )
            else None
        )


class FakeProvider:
    descriptor = SimpleNamespace(name="fake")

    def __init__(self):
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResult(
            "1", ProviderMessage("assistant", "answer"), ProviderUsage(1, 1, 0, 0, 0)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "domain,purpose,expected_preferences",
    [
        ("operations", "assistant_response", True),
        ("operations", "intent", False),
        ("customer-service", "assistant_response", True),
        ("hr", "evaluate", False),
    ],
)
async def test_actual_final_request_counts_selected_memory_and_hr_evaluation_excludes_preferences(
    tmp_path, domain, purpose, expected_preferences
):
    node = (
        "customer-service:answer_general" if domain == "customer-service" else "direct"
    )
    now = int(time())
    scope = ConversationScope("t", "u", domain, domain, "TASK_ONLY", None)
    a = SourceDependency("USER_PREFERENCE_DECISION", "A", "1", 0, 1, 0)
    b = SourceDependency("USER_PREFERENCE_DECISION", "B", "1", 0, 1, 0)
    current = SourceDependency("CURRENT_INPUT", "input", "1", 0, 1, 0)
    packet = MemoryContextPacket(
        "packet",
        1,
        scope,
        "java-task",
        "java-execution",
        "memory/3",
        1,
        now,
        now + 50,
        0,
        0,
        0,
        "semantic",
        "parent",
        (
            MemoryReference("a", "1", "response.language", "zh-CN", (a,)),
            MemoryReference("b", "1", "response.format", "bullets", (b,)),
        ),
        (a, b, current),
    )
    policy = MemoryPolicy(
        "memory",
        "memory/3",
        domain,
        frozenset({domain}),
        readable_layers=frozenset({"semantic"}),
        allowed_scopes=frozenset({"USER_PRIVATE"}),
        field_allowlist=frozenset({"response.language", "response.format"}),
        source_types=frozenset({"USER_PREFERENCE_DECISION", "CURRENT_INPUT"}),
    )
    context = MemoryExecutionContext(
        packet,
        policy,
        (MemoryExecutionGrant(node, domain, purpose),),
        now + 90,
        memory_packet_digest(packet),
        memory_packet_semantic_digest(packet),
        "a" * 64,
        (current, a) if purpose == "intent" else (current,),
    )
    authority = LocalAuthority(
        MemoryExecutionRecord(
            context,
            "python-run",
            "OPERATIONS",
            "a" * 64,
            now + 80,
            "ACTIVE",
            1,
            0,
            0,
            0,
        )
    )
    manifests = MySqlContextManifestStore(LocalEngine(tmp_path / "context.db"))
    counter = Counter()
    controller = ContextController(
        counter, manifests, b"k" * 32, validator=StoredMemoryPacketValidator(authority)
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
        "1",
        "1",
        "1",
        0,
        capacity,
        WindowLimits(5000, None, 100, 0, 4900),
        JsonObject(),
    )
    dispatch = ContextDispatch(
        controller,
        manifests,
        ServerDispatchAuthority(
            {("fake", "fake", node): metadata},
            {node: (domain, purpose)},
            memory_execution_store=authority,
        ),
    )
    model = FakeProvider()
    provider = ControlledModelProvider(
        model, dispatch, "fake", "fake", paid_transport=False
    )
    binding = RunContextBinding(scope, "java-task", "java-execution", now + 80, context)
    request = ProviderRequest(
        "1",
        (ProviderMessage("user", "current facts and scoring rules"),),
        JsonObject(),
        1000,
    )
    with bind_run_context(binding), model_stage("operation", b"frozen", node_id=node):
        await provider.complete(request)
    assert len(model.requests) == 1
    sent = model.requests[0]
    assert (len(sent.messages) == 3) is expected_preferences
    if not expected_preferences:
        assert sent == request
    receipt_scope = replace(binding.memory_context.packet.scope)
    from efficiency_platform_agent.core.memory import ExecutionScope

    execution_scope = ExecutionScope(
        receipt_scope, "java-task", "java-execution", node, purpose, domain
    )
    receipt = await manifests.get_operation_receipt(execution_scope, "operation")
    assert receipt.status == "SUCCEEDED"
    if purpose == "intent":
        recorded = await manifests.execution_manifests("t", "java-execution")
        assert set(recorded[0].safety_dependencies) == {current, a}
    authority.record = replace(authority.record, state="REVOKED", deletion_epoch=1)
    with (
        bind_run_context(binding),
        model_stage("next-operation", b"frozen", node_id=node),
        pytest.raises(ValueError, match="REVOKED"),
    ):
        await provider.complete(request)
    assert len(model.requests) == 1
