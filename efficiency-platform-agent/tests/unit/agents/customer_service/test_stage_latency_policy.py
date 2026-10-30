"""充分性等待优化不改变冲突核验的模型选项。"""

import json
from types import SimpleNamespace

import pytest
from test_evidence_pack import bundle

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
)
from efficiency_platform_agent.agents.customer_service.state import SufficiencyDecision
from efficiency_platform_agent.core.run import JsonObject, ProviderStreamChunk


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("stage", ["sufficiency", "conflict_screen"])
async def test_sufficiency_uses_direct_inference_but_conflicts_keep_default(
    streaming, stage
):
    requests = []
    content = json.dumps(
        {
            "sufficient": False,
            "supported_claims": [],
            "unsupported_claims": ["没有公司依据"],
            "conflicts": [],
            "recommended_mode": "INSUFFICIENT_EVIDENCE",
        }
    )

    class Provider:
        async def complete(self, request):
            requests.append(request)
            return SimpleNamespace(error=None, message=SimpleNamespace(content=content))

        async def stream(self, request):
            requests.append(request)
            yield ProviderStreamChunk(delta=content, finish_reason="stop")

    config = bundle()
    config.prompt_bindings += (
        config.prompt_bindings[0].model_copy(update={"stage_key": "conflict_screen"}),
    )
    gateway = ReleaseStructuredModelGateway(Provider(), config)
    if streaming:
        await gateway.stream_complete(stage, {}, SufficiencyDecision, lambda _: None)
    else:
        await gateway.complete(stage, {}, SufficiencyDecision)
    options = dict(requests[0].options.items)
    if stage == "sufficiency":
        assert options["thinking"] == JsonObject((("type", "disabled"),))
    else:
        assert "thinking" not in options
