"""运营 Agent 真实联网验收矩阵。

本脚本只允许调用已经启动的真实 FastAPI Agent，不提供 Fake、Mock 或离线
回退模式。研究相关用例在 DeepSeek Web Search Gate 未启用或配置不完整时，
统一标记为 ``BLOCKED_CONFIGURATION``，绝不把阻断伪装成成功。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from efficiency_platform_agent.configuration.integration import (
    IntegrationGate,
    S7IntegrationSettings,
)
from scripts.operation_chat_acceptance import AcceptanceOptions, run_acceptance

_PLATFORMS = (
    "wechat_official_account",
    "xiaohongshu",
    "toutiao",
)


@dataclass(frozen=True)
class AcceptanceCase:
    """一个真实对话验收用例的稳定定义。"""

    case_id: str
    message: str
    expect: Literal["succeeded", "clarification"]
    requires_research: bool = False
    platforms: tuple[str, ...] = ()
    expect_failure_or_degradation: bool = False
    preceding_messages: tuple[str, ...] = ()


ACCEPTANCE_CASES: dict[str, AcceptanceCase] = {
    "R01": AcceptanceCase(
        "R01",
        "你是谁？",
        "succeeded",
    ),
    "R02": AcceptanceCase(
        "R02",
        "请为新品写公众号、小红书和头条三种独立版本的发布文案，不需要联网。",
        "succeeded",
        platforms=_PLATFORMS,
    ),
    "R03": AcceptanceCase(
        "R03",
        "收集下周 AI 行业热点，整理成公众号、小红书和头条三种版本。",
        "succeeded",
        requires_research=True,
        platforms=_PLATFORMS,
    ),
    "R04": AcceptanceCase(
        "R04",
        "整理最近 7 天 AI 行业动态，生成一份带来源的公众号周报。",
        "succeeded",
        requires_research=True,
        platforms=("wechat_official_account",),
    ),
    "R05": AcceptanceCase(
        "R05",
        "为我们的新品牌制定品牌定位、IP 人设和首月活动策划。",
        "clarification",
    ),
    "R06": AcceptanceCase(
        "R06",
        "制定下周的内容日历和选题规划，按日期、平台、主题和目标输出。",
        "clarification",
    ),
    "R07": AcceptanceCase(
        "R07",
        "把上一版文案改得更专业一些，并保留原有的三个重点。",
        "succeeded",
        platforms=_PLATFORMS,
        preceding_messages=(
            "请为新品写公众号、小红书和头条三种独立版本的发布文案，不需要联网。",
        ),
    ),
    "R08": AcceptanceCase(
        "R08",
        "在研究来源不足或研究服务超时时，收集最近 7 天 AI 热点并生成摘要。",
        "succeeded",
        requires_research=True,
        expect_failure_or_degradation=True,
    ),
}


def _blocked(reason: str, missing: tuple[str, ...] = ()) -> dict[str, Any]:
    """生成不带敏感配置的真实门禁阻断结果。"""

    return {
        "status": "BLOCKED_CONFIGURATION",
        "reason": reason,
        "missing": list(missing),
        "execution_mode": "real",
        "fake_fallback": False,
    }


def inspect_real_configuration(env_file: Path | None = None) -> dict[str, Any]:
    """检查真实研究能力配置，只返回 Gate 状态和缺失键名称。"""

    target = env_file or PROJECT_ROOT / ".env"
    if not target.is_file():
        return _blocked("ENV_FILE_MISSING")
    try:
        settings = S7IntegrationSettings.from_env_file(target)
    except (OSError, UnicodeError, ValueError, TypeError):
        return _blocked("ENV_FILE_INVALID")

    gate = IntegrationGate.DEEPSEEK_WEB_SEARCH
    if not settings.gates.get(gate.value, False):
        return _blocked("RESEARCH_GATE_DISABLED")
    missing = settings.for_gate(gate)
    if missing:
        return _blocked("CONFIGURATION_MISSING", missing)
    return {
        "status": "READY",
        "gate": gate.value,
        "execution_mode": "real",
        "fake_fallback": False,
    }


def _platforms_pass(case: AcceptanceCase, summary: dict[str, Any]) -> bool:
    """校验多平台交付物数量；正文内容不进入验收证据。"""

    if not case.platforms:
        return True
    expected = len(case.platforms)
    return (
        summary.get("deliverable_count") == expected
        and summary.get("citation_count", 0) >= (1 if case.requires_research else 0)
    )


def classify_case_result(
    case: AcceptanceCase, summary: dict[str, Any]
) -> dict[str, Any]:
    """依据安全白名单摘要分类，不把 HTTP 成功等同于业务成功。"""

    result: dict[str, Any] = {
        "case_id": case.case_id,
        "message": case.message,
        "execution_mode": "real",
        "summary": summary,
    }
    if case.expect_failure_or_degradation:
        if summary.get("status") in {"failed", "degraded_succeeded"}:
            result["status"] = "PASS"
            return result
        result["status"] = "NOT_EXECUTED"
        result["reason"] = "FAILURE_INJECTION_NOT_OBSERVED"
        return result
    if not summary.get("passed"):
        result["status"] = "FAIL"
        result["error_code"] = summary.get("error_code", "ACCEPTANCE_FAILED")
        return result
    expected_statuses = (
        {"waiting_input"}
        if case.expect == "clarification"
        else {"succeeded", "degraded_succeeded"}
    )
    if summary.get("status") not in expected_statuses:
        result["status"] = "FAIL"
        result["error_code"] = "UNEXPECTED_STATUS"
        return result
    if case.requires_research and summary.get("citation_count", 0) <= 0:
        result["status"] = "FAIL"
        result["error_code"] = "RESEARCH_EVIDENCE_MISSING"
        return result
    if not _platforms_pass(case, summary):
        result["status"] = "FAIL"
        result["error_code"] = "PLATFORM_DELIVERABLE_CHECK_FAILED"
        return result
    result["status"] = "PASS"
    return result


def _validate_case_ids(case_ids: Sequence[str]) -> tuple[str, ...]:
    """校验命令行用例编号，拒绝未知编号和空集合。"""

    selected = tuple(case_ids)
    if not selected or any(case_id not in ACCEPTANCE_CASES for case_id in selected):
        raise ValueError("INVALID_CASE_IDS")
    return selected


async def run_live_matrix(
    *,
    base_url: str,
    case_ids: Sequence[str] = tuple(ACCEPTANCE_CASES),
    tenant: str = "real-acceptance-tenant",
    user: str = "real-acceptance-user",
    timeout_seconds: float = 180.0,
    env_file: Path | None = None,
) -> dict[str, Any]:
    """执行真实 HTTP/SSE 矩阵；不接受 transport 注入，保证不会切 Fake。"""

    selected = _validate_case_ids(case_ids)
    configuration = inspect_real_configuration(env_file)
    results: list[dict[str, Any]] = []
    for case_id in selected:
        case = ACCEPTANCE_CASES[case_id]
        if case.requires_research and configuration["status"] != "READY":
            result = {
                "case_id": case.case_id,
                "message": case.message,
                **configuration,
            }
            results.append(result)
            continue
        options = AcceptanceOptions(
            base_url=base_url,
            tenant=tenant,
            user=user,
            conversation=f"real-acceptance-{case.case_id.lower()}",
            message=case.message,
            expect=case.expect,
            expect_three_platforms=len(case.platforms) == 3,
            timeout_seconds=timeout_seconds,
        )
        preceding_summaries: list[dict[str, Any]] = []
        for preceding_message in case.preceding_messages:
            preceding_options = AcceptanceOptions(
                base_url=base_url,
                tenant=tenant,
                user=user,
                conversation=options.conversation,
                message=preceding_message,
                expect="succeeded",
                timeout_seconds=timeout_seconds,
            )
            preceding_summary = await run_acceptance(
                preceding_options, include_details=True
            )
            preceding_summaries.append(preceding_summary)
            if not preceding_summary.get("passed"):
                results.append(
                    {
                        "case_id": case.case_id,
                        "message": case.message,
                        "execution_mode": "real",
                        "status": "FAIL",
                        "error_code": "PRECEDING_TURN_FAILED",
                        "preceding_turns": preceding_summaries,
                    }
                )
                break
        else:
            summary = await run_acceptance(options, include_details=True)
            result = classify_case_result(case, summary)
            if preceding_summaries:
                result["preceding_turns"] = preceding_summaries
            results.append(result)
    return {
        "contract_version": "operation.real.acceptance/1",
        "execution_mode": "real",
        "fake_fallback": False,
        "configuration": configuration,
        "cases": results,
    }


class _SafeArgumentParser(argparse.ArgumentParser):
    """避免 argparse 将密钥或完整输入回显到异常文本。"""

    def error(self, message: str) -> NoReturn:
        raise ValueError("INVALID_ARGUMENTS")


def _exit_code(report: dict[str, Any]) -> int:
    """按验收状态返回稳定进程码。"""

    statuses = {item.get("status") for item in report.get("cases", [])}
    if "FAIL" in statuses:
        return 2
    if "BLOCKED_CONFIGURATION" in statuses or report["configuration"]["status"] != "READY":
        return 3
    if "NOT_EXECUTED" in statuses:
        return 4
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """运行真实矩阵并写入脱敏 JSON 证据。"""

    parser = _SafeArgumentParser(description="运营 Agent 真实联网验收矩阵")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--cases", default=",".join(ACCEPTANCE_CASES))
    parser.add_argument("--tenant", default="real-acceptance-tenant")
    parser.add_argument("--user", default="real-acceptance-user")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT
        / "docs/superpowers/acceptance/evidence/2026-09-09-运营Agent受控混合升级-真实验收.json",
    )
    try:
        args = parser.parse_args(argv)
        report = asyncio.run(
            run_live_matrix(
                base_url=args.base_url,
                case_ids=tuple(value for value in args.cases.split(",") if value),
                tenant=args.tenant,
                user=args.user,
                timeout_seconds=args.timeout_seconds,
                env_file=args.env_file,
            )
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    except (ValueError, OSError):
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return _exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
