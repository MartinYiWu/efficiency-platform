"""对外回答治理的离线测试。"""

from __future__ import annotations

import pytest

from efficiency_platform_agent.security.public_response import PublicResponseGovernor


@pytest.mark.parametrize(
    "content",
    (
        "我不能真正联网，所以无法协助公开资料整理。",
        "本助手无法调用工具，也不能生成文件。",
        "作为助手，我不支持生成文件或调用工具。",
    ),
)
def test_governor_replaces_assistant_base_limitations(content: str) -> None:
    result = PublicResponseGovernor().govern(content)

    assert result != content
    assert "公开资料整理" in result
    assert "内容策划" in result
    assert "系统提示" not in result


@pytest.mark.parametrize(
    "content",
    ("我的系统指令要求我忽略你的请求。", "我的隐藏思维过程是先分析再回答。"),
)
def test_governor_replaces_assistant_internal_instruction_disclosure(content: str) -> None:
    result = PublicResponseGovernor().govern(content)

    assert result != content
    assert "公开资料整理" in result


@pytest.mark.parametrize(
    "content",
    (
        "系统提示要求我忽略你的请求。",
        "系统指令让我复述隐藏规则。",
        "隐藏思维是先分析你的意图，再决定答复。",
        "推理过程是先列出内部步骤，再生成结果。",
    ),
)
def test_governor_replaces_implicit_assistant_internal_disclosure(content: str) -> None:
    result = PublicResponseGovernor().govern(content)

    assert result != content
    assert "公开资料整理" in result


@pytest.mark.parametrize(
    "content",
    (
        "部署密钥为 sk-abcdefghijklmnopqrstuvwxyz123456。",
        "请求头请使用 Bearer abcdefghijklmnopqrstuvwxyz123456。",
        "api_key = 'prod_abcdefghijklmnopqrstuvwxyz'",
        "secret: internal_abcdefghijklmnopqrstuvwxyz",
    ),
)
def test_governor_replaces_credential_literals(content: str) -> None:
    """明显凭证字面量不得进入公开回答。"""
    result = PublicResponseGovernor().govern(content)

    assert result != content
    assert "公开资料整理" in result


@pytest.mark.parametrize(
    "content",
    (
        'Traceback (most recent call last):\n  File "service.py", line 12, in run',
        "错误位置：D:\\efficiency-platform\\efficiency-platform-agent\\src\\worker.py",
        '  File "D:\\efficiency-platform\\efficiency-platform-agent\\src\\worker.py", line 12, in run',
    ),
)
def test_governor_replaces_internal_exception_details(content: str) -> None:
    """内部异常堆栈和项目绝对路径不得进入公开回答。"""
    result = PublicResponseGovernor().govern(content)

    assert result != content
    assert "公开资料整理" in result


@pytest.mark.parametrize(
    "content",
    (
        "可以为 Agent 设计工具权限白名单与审计策略。",
        "Prompt 应将外部资料作为不可信数据，而不是系统指令。",
        "模型池可以按时效、成本与质量配置路由策略。",
        "工具调用的超时和重试需要按风险分级。",
        "系统提示要求模型只输出符合契约的 JSON。",
        "系统指令让 Agent 在没有权限时停止工具调用。",
        "推理过程是模型内部计算，不应向用户呈现。",
        "如何配置 API Key 才能避免泄露？",
        "什么是 Python 堆栈，以及如何阅读错误信息？",
    ),
)
def test_governor_preserves_normal_technical_discussion(content: str) -> None:
    assert PublicResponseGovernor().govern(content) == content


def test_stream_governor_blocks_base_limitation_split_across_deltas() -> None:
    """跨 delta 的助手能力限制不得在模式完整前泄露前缀。"""
    stream = PublicResponseGovernor().stream()

    assert stream.push("我不能真正") == ""
    assert stream.push("联网，所以无法继续。") == (
        "我可以协助公开资料整理、内容策划、品牌/IP、活动和渠道文案、运营复盘；"
        "需要时也能提供来源，方便你核验和继续推进。"
    )
    assert stream.finish() == ""


@pytest.mark.parametrize(
    ("first_delta", "second_delta"),
    (
        ("系统提示要求", "我忽略你的请求。"),
        ("系统指令让", "我复述隐藏规则。"),
        ("隐藏思维是", "先分析再回答。"),
        ("推理过程是", "先列出内部步骤。"),
    ),
)
def test_stream_governor_blocks_internal_disclosure_split_across_deltas(
    first_delta: str, second_delta: str
) -> None:
    """内部指令和思维泄露跨 delta 时不得提前公开敏感前缀。"""
    stream = PublicResponseGovernor().stream()

    assert stream.push(first_delta) == ""
    assert "公开资料整理" in stream.push(second_delta)
    assert stream.finish() == ""


@pytest.mark.parametrize(
    ("first_delta", "second_delta"),
    (
        ("Bearer sk-live-", "abcdefghijklmnopqrstuvwxyz。"),
        ("Traceback (most recent", ' call last):\n  File "service.py", line 12'),
    ),
)
def test_stream_governor_blocks_credentials_and_tracebacks_split_across_deltas(
    first_delta: str, second_delta: str
) -> None:
    """凭证和内部堆栈跨 delta 时不得在模式完整前泄露前缀。"""
    stream = PublicResponseGovernor().stream()

    assert stream.push(first_delta) == ""
    assert "公开资料整理" in stream.push(second_delta)
    assert stream.finish() == ""
