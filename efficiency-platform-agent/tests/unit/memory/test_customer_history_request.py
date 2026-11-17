"""客服一般建议通过真实回答生成和Release网关保留已授权历史，关闭开关沿旧行为。"""

import json
from dataclasses import replace
from time import time

import pytest

from efficiency_platform_agent.agents.customer_service.answer import generate_answer
from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.state import (
    HistoryMessage,
    IntentDecision,
)
from efficiency_platform_agent.core.memory_execution import MemoryExecutionGrant
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)
from tests.integration.context_control.business_http_fixture import release_bundle
from tests.integration.context_control.test_memory_execution_mysql import context


class Boundary(FakeModelProvider):
    def __init__(self):
        super().__init__("history-test", [])
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return ProviderResult(
            request.contract_version,
            ProviderMessage(
                "assistant",
                json.dumps(
                    {
                        "contract_version": "customer-service-answer/1",
                        "answer_mode": "GENERAL_ADVICE",
                        "general_advice": {"paragraphs": ["synthetic answer"]},
                    }
                ),
            ),
            ProviderUsage(1, 1, 0, 0, 0),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_general_advice_actual_gateway_request_preserves_controlled_history(
    enabled,
):
    memory = context()
    scope = replace(
        memory.packet.scope,
        domain="customer-service",
        top_level_agent_id="customer-service",
    )
    packet = replace(memory.packet, scope=scope)
    memory = replace(
        memory,
        packet=packet,
        policy=replace(
            memory.policy,
            domain="customer-service",
            agent_ids=frozenset({"customer-service"}),
        ),
        execution_grants=(
            MemoryExecutionGrant(
                "customer-service:answer_general",
                "customer-service",
                "assistant_response",
            ),
        ),
        packet_digest=memory_packet_digest(packet),
        semantic_snapshot_digest=memory_packet_semantic_digest(packet),
    )
    binding = RunContextBinding(
        scope,
        packet.task_id,
        packet.execution_id,
        int(time()) + 90,
        memory if enabled else None,
    )
    boundary = Boundary()
    gateway = ReleaseStructuredModelGateway(boundary, release_bundle())
    intent = IntentDecision(
        intent_type="GENERAL_QUERY",
        requires_company_knowledge=False,
        requires_general_advice=True,
        normalized_question="continue",
    )
    history = (
        HistoryMessage(role="user", content="authorized previous user"),
        HistoryMessage(role="assistant", content="authorized previous answer"),
    )
    with bind_run_context(binding):
        await generate_answer(
            gateway,
            question="continue",
            intent=intent,
            evidence=(),
            sufficiency=None,
            history=history,
        )
    assert len(boundary.requests) == 1
    sent = "\n".join(str(message.content) for message in boundary.requests[0].messages)
    assert ("authorized previous user" in sent) is enabled
    assert ("authorized previous answer" in sent) is enabled
