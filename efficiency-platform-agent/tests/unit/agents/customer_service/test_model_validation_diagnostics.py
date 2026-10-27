"""结构化校验诊断只包含契约字段位置与错误类型。"""

import json
import logging
from types import SimpleNamespace

import pytest
from test_evidence_pack import bundle

from efficiency_platform_agent.agents.customer_service.model_gateway import (
    ReleaseStructuredModelGateway,
    StructuredModelError,
)
from efficiency_platform_agent.agents.customer_service.state import (
    CustomerServiceAnswer,
)
from efficiency_platform_agent.core.run import ProviderStreamChunk


@pytest.mark.parametrize("streaming", [False, True])
async def test_validation_diagnostics_never_log_model_input_or_untrusted_field_names(
    caplog, streaming
):
    content = json.dumps(
        {
            "contract_version": "customer-service-answer/1",
            "answer_mode": "GENERAL_ADVICE",
            "knowledge_gap": 12,
            "general_advice": {"paragraphs": [{"private": "MODEL_BODY_SECRET"}]},
            "KEY_SECRET_SHOULD_NOT_BE_LOGGED": "MODEL_BODY_SECRET",
        }
    )

    class Provider:
        async def complete(self, request):
            return SimpleNamespace(error=None, message=SimpleNamespace(content=content))

        async def stream(self, request):
            yield ProviderStreamChunk(delta=content, finish_reason="stop")

    gateway = ReleaseStructuredModelGateway(Provider(), bundle())
    with (
        caplog.at_level(logging.WARNING, logger="efficiency_platform_agent.execution"),
        pytest.raises(StructuredModelError, match="模型返回不符合契约"),
    ):
        if streaming:
            await gateway.stream_complete(
                "answer_mixed",
                {"question": "INPUT_QUESTION_SECRET"},
                CustomerServiceAnswer,
                lambda _: None,
            )
        else:
            await gateway.complete(
                "answer_mixed",
                {"question": "INPUT_QUESTION_SECRET"},
                CustomerServiceAnswer,
            )
    assert "customer_service_model_contract_invalid" in caplog.text
    assert "stage=answer_mixed" in caplog.text
    assert "knowledge_gap" in caplog.text
    assert "general_advice" in caplog.text
    assert "paragraphs" in caplog.text
    assert "string_type" in caplog.text
    assert "extra_forbidden" in caplog.text
    assert "[unknown_field]" in caplog.text
    for private in (
        "MODEL_BODY_SECRET",
        "INPUT_QUESTION_SECRET",
        "KEY_SECRET_SHOULD_NOT_BE_LOGGED",
    ):
        assert private not in caplog.text
