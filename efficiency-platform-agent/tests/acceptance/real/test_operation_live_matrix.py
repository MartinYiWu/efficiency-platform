"""运营 Agent 真实验收矩阵的门禁与分类测试。

这些测试只验证验收编排器的安全边界，不发起真实网络请求。真实请求必须
通过 ``scripts/real_operation_acceptance.py`` 显式执行。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scripts.operation_chat_acceptance import AcceptanceOptions, run_acceptance
from scripts.real_operation_acceptance import (
    ACCEPTANCE_CASES,
    classify_case_result,
    inspect_real_configuration,
)


def test_live_matrix_contains_eight_cases_and_exact_research_request() -> None:
    """矩阵覆盖八类场景，R03 必须保留用户指定的真实输入。"""
    assert tuple(ACCEPTANCE_CASES) == (
        "R01",
        "R02",
        "R03",
        "R04",
        "R05",
        "R06",
        "R07",
        "R08",
    )
    assert (
        ACCEPTANCE_CASES["R03"].message
        == "收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本。"
    )
    assert ACCEPTANCE_CASES["R03"].requires_research is True
    assert set(ACCEPTANCE_CASES["R03"].platforms) == {
        "wechat_official_account",
        "xiaohongshu",
        "toutiao",
    }
    assert ACCEPTANCE_CASES["R07"].preceding_messages


def test_missing_real_key_is_blocked_configuration_not_fake(tmp_path: Path) -> None:
    """真实配置缺失必须阻断研究用例，不能静默降级为 Fake。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENT_S7_GATE_DEEPSEEK_WEB_SEARCH=true\n"
        "AGENT_LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
        "AGENT_LLM_DEEPSEEK_FAST_MODEL=deepseek-chat\n"
        "AGENT_LLM_DEEPSEEK_BALANCED_MODEL=deepseek-chat\n"
        "AGENT_LLM_DEEPSEEK_STRONG_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )

    result = inspect_real_configuration(env_file)

    assert result["status"] == "BLOCKED_CONFIGURATION"
    assert result["reason"] == "CONFIGURATION_MISSING"
    assert "AGENT_LLM_DEEPSEEK_API_KEY" in result["missing"]
    assert result["execution_mode"] == "real"
    assert result["fake_fallback"] is False


def test_disabled_research_gate_is_blocked_configuration(tmp_path: Path) -> None:
    """研究 Gate 关闭时只允许明确阻断，不得伪造联网成功。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AGENT_S7_GATE_DEEPSEEK_WEB_SEARCH=false\n",
        encoding="utf-8",
    )

    result = inspect_real_configuration(env_file)

    assert result["status"] == "BLOCKED_CONFIGURATION"
    assert result["reason"] == "RESEARCH_GATE_DISABLED"
    assert result["fake_fallback"] is False


def test_research_without_citations_cannot_be_marked_pass() -> None:
    """真实研究即使 HTTP 成功，也必须存在引用才可通过。"""
    case = ACCEPTANCE_CASES["R03"]
    result = classify_case_result(
        case,
        {
            "passed": True,
            "status": "succeeded",
            "citation_count": 0,
            "deliverable_count": 3,
            "degraded": False,
        },
    )

    assert result["status"] == "FAIL"
    assert result["error_code"] == "RESEARCH_EVIDENCE_MISSING"


def test_degraded_success_is_successful_for_normal_case() -> None:
    """模型降级但仍完成交付时，普通成功用例不能被误判为失败。"""
    result = classify_case_result(
        ACCEPTANCE_CASES["R02"],
        {
            "passed": True,
            "status": "degraded_succeeded",
            "citation_count": 0,
            "deliverable_count": 3,
            "degraded": True,
        },
    )

    assert result["status"] == "PASS"


async def test_acceptance_details_keep_run_and_event_sequence_without_body() -> None:
    """真实证据需要 Run 与事件序列，但不能把模型正文写入摘要。"""

    def endpoint(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return httpx.Response(
                201,
                json={
                    "contract_version": "conversation/1",
                    "conversation_id": "real-test-conversation",
                    "turn_id": "real-test-turn",
                    "run_id": "real-test-run",
                    "status": "queued",
                },
            )
        if request.url.path.endswith("/events"):
            def frame(sequence: int, name: str, payload: dict[str, object]) -> str:
                envelope = {
                    "contract_version": "run.stream.event/1",
                    "event": name,
                    "run_id": "real-test-run",
                    "sequence": sequence,
                    "payload": payload,
                }
                return (
                    f"id: {sequence}\n"
                    f"event: {name}\n"
                    f"data: {json.dumps(envelope)}\n\n"
                )

            return httpx.Response(
                200,
                text=frame(1, "run_started", {"status": "running"})
                + frame(
                    2,
                    "assistant_delta",
                    {"delta": "不应写入证据正文"},
                )
                + frame(3, "stream_done", {"status": "succeeded", "degraded": False}),
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={
                "contract_version": "run.view/1",
                "run_id": "real-test-run",
                "request_id": "real-test-request",
                "status": "succeeded",
                "strategy": "direct",
                "output": None,
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "cost_microunits": 0,
                    "estimated": True,
                },
            },
        )

    result = await run_acceptance(
        AcceptanceOptions(
            base_url="http://agent.test",
            tenant="real-test-tenant",
            user="real-test-user",
            conversation="real-test-conversation",
            message="真实验收详情测试",
        ),
        transport=httpx.MockTransport(endpoint),
        include_details=True,
    )

    assert result["run_id"] == "real-test-run"
    assert result["event_sequence"] == [
        "run_started",
        "assistant_delta",
        "stream_done",
    ]
    assert "不应写入证据正文" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("case_id", ["R01", "R02", "R05", "R06", "R07"])
def test_non_research_cases_do_not_require_web_search(case_id: str) -> None:
    """非研究用例不能因研究 Gate 缺失而被错误标记为研究阻断。"""
    assert ACCEPTANCE_CASES[case_id].requires_research is False
