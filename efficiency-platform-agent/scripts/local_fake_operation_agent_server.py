"""启动仅供浏览器验收的确定性运营 Agent，不读取环境配置或访问外网。"""

from __future__ import annotations

import argparse
import json

import uvicorn
from pydantic import SecretStr

from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.core.run import (
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.harness.local_real_factory import (
    build_local_agent_application,
)
from efficiency_platform_agent.providers.llm.fake import FakeModelProvider


def _intent() -> dict[str, object]:
    """返回单平台内容场景的完整结构化意图。"""
    return {
        "contract_version": "intent/1",
        "domain": "内容",
        "goal": "生成新品内容",
        "task_type": "multi_platform_content",
        "channels": ["xiaohongshu"],
        "audience": "通勤女性",
        "style": "轻松实用",
        "time_range": None,
        "needs_research": False,
        "needs_multi_agent": True,
        "missing_fields": [],
        "needs_clarification": False,
        "confidence": 0.99,
        "model_hint": "balanced",
        "requirements": {
            "contract_version": "intent.requirements/1",
            "topic": "环保水杯新品",
            "time_window": None,
            "platforms": ["xiaohongshu"],
            "brand": None,
            "product": "环保水杯",
            "goal": "新品种草",
            "planning_window": None,
            "ip": None,
            "audience": "通勤女性",
            "incubation_window": None,
            "campaign_goal": None,
            "campaign_window": None,
            "topic_scope": None,
            "calendar_window": None,
            "growth_goal": None,
            "funnel_stage": None,
            "experiment_window": None,
            "review_window": None,
            "metric_definition": None,
        },
    }


def _deliverable() -> dict[str, object]:
    """返回可由质量门直接校验的确定性运营成品。"""
    return {
        "contract_version": "deliverable/1",
        "platform": "xiaohongshu",
        "title": "通勤补水新搭子",
        "body": "轻巧环保的水杯，让每天通勤补水更简单。",
        "hashtags": ["#通勤好物", "#环保水杯"],
        "format_notes": ["移动端短段落"],
        "citations": [],
        "warnings": [],
    }


def _result(version: str, payload: dict[str, object]) -> ProviderResult:
    """把合成 JSON 转换为正式 Provider 契约。"""
    return ProviderResult(
        version,
        ProviderMessage("assistant", json.dumps(payload, ensure_ascii=False)),
        ProviderUsage(12, 24, 0, 0, 0),
    )


def _settings() -> S7IntegrationSettings:
    """构造不具备真实网络意义的合成配置。"""
    return S7IntegrationSettings(
        deepseek_base_url=SecretStr("https://synthetic.invalid"),
        deepseek_api_key=SecretStr("synthetic-key"),
        deepseek_fast_model=SecretStr("synthetic-fast"),
        deepseek_balanced_model=SecretStr("synthetic-balanced"),
        deepseek_strong_model=SecretStr("synthetic-strong"),
    )


def main() -> None:
    """启动显式 test_mode 组合根。"""
    parser = argparse.ArgumentParser(description="启动确定性运营 Agent 验收服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()
    provider = FakeModelProvider(
        "operation-browser-acceptance",
        [
            _result("intent-model/1", _intent()),
            _result("operation-model/1", _deliverable()),
        ],
    )
    bundle = build_local_agent_application(
        _settings(), provider=provider, test_mode=True
    )
    uvicorn.run(bundle.app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
