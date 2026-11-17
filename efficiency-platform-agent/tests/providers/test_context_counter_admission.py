"""用现有费用上界校验上下文计数不退化，不发送外部请求。"""

import json
from dataclasses import replace

from efficiency_platform_agent.core.run import ProviderMessage
from efficiency_platform_agent.providers.llm.deepseek import _serialize_message
from efficiency_platform_agent.providers.llm.request_counter import (
    ConservativeRequestTokenCounter,
)
from efficiency_platform_agent.providers.paid_usage import input_token_upper_bound
from tests.unit.context.test_request_counter import capacity, request


def test_counter_covers_existing_paid_guard_and_developer_role_serialization():
    counter = ConservativeRequestTokenCounter()
    source = request("中文🙂\n程序与JSON合成材料" * 30)
    source = replace(
        source,
        messages=source.messages
        + (ProviderMessage("developer", "合成输出Schema要求"),),
    )
    measured = counter.measure(source, capacity()).total_upper_bound
    for supports_developer in (True, False):
        messages = [
            _serialize_message(item, supports_developer_role=supports_developer)
            for item in source.messages
        ]
        payload = {"model": capacity().model, "messages": messages}
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        assert measured >= input_token_upper_bound("deepseek", body, payload)
