"""DeepSeek 服务端 web_search 研究 Provider。

该适配器只消费模型返回的来源字段，绝不根据来源 URL 发起网页请求。
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from openai import APITimeoutError

from efficiency_platform_agent.agents.operation.contracts.evidence import (
    EvidenceDuplicateStatus,
    EvidenceQualityStatus,
    normalize_evidence_url,
)
from efficiency_platform_agent.agents.operation.contracts.task import SourceScope
from efficiency_platform_agent.capabilities.research.contracts import (
    ResearchObservation,
    ResearchProviderPort,
    ResearchRequest,
    ResearchResult,
    ResearchStatus,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    DiagnosticRecorderPort,
    NoopDiagnosticRecorder,
    safe_exception_location,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot

_EMPTY_USAGE = UsageSnapshot()


def _field(value: Any, name: str, default: Any = None) -> Any:
    """同时读取 SDK 对象和字典字段。"""
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class DeepSeekWebSearchProvider(ResearchProviderPort):
    """使用注入的 Responses 客户端调用服务端 web_search。"""

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        timeout_ms: int = 240_000,
        recorder: DiagnosticRecorderPort | None = None,
    ) -> None:
        if client is None:
            raise ValueError("client不能为空")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            raise ValueError("timeout_ms必须为正整数")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model不能为空")
        self.client = client
        self.model = model
        self.timeout_ms = timeout_ms
        self.recorder = recorder or NoopDiagnosticRecorder()

    async def research(self, request: ResearchRequest) -> ResearchResult:
        """请求服务端搜索并将来源映射为 S5 ResearchObservation。"""
        if not isinstance(request, ResearchRequest):
            raise TypeError("request必须是ResearchRequest")
        responses = getattr(self.client, "responses", None)
        if responses is None or not hasattr(responses, "create"):
            self._record(
                "research_invocation_failed",
                DiagnosticLevel.ERROR,
                stage="responses.create",
                error_code="RESEARCH_RESPONSES_UNSUPPORTED",
                error_type="ResponsesUnsupported",
                retryable=False,
                attempt=1,
            )
            return self._failed(request, "RESEARCH_UNAVAILABLE")
        provider_call_id = f"research-{uuid.uuid4().hex}"
        started_at_ns = time.monotonic_ns()
        self._record(
            "research_invocation_started",
            DiagnosticLevel.INFO,
            stage="responses.create",
            provider_call_id=provider_call_id,
            attempt=1,
        )
        try:
            response = await responses.create(
                model=self.model,
                input=(
                    f"今天日期：{datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()}\n"
                    f"研究目标：{request.goal}\n"
                    "请只围绕上述研究目标检索今天及最近24小时内的公开信息；"
                    "优先选择官方公告、主流新闻媒体或厂商原始发布，避免日期工具、"
                    "聚合转载和与主题无关的页面。每条事实都必须附带来源标题、"
                    "发布者和完整 URL，未找到可复核来源时明确返回无来源。"
                ),
                tools=[{"type": "web_search_2025_08_26"}],
                tool_choice={"type": "web_search_2025_08_26"},
                max_output_tokens=request.max_output_tokens,
                timeout=self.timeout_ms / 1000,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001, 不传播厂商异常
            error_code, retryable, http_status = _classify_invocation_error(error)
            self._record(
                "research_invocation_failed",
                DiagnosticLevel.ERROR,
                stage="responses.create",
                provider_call_id=provider_call_id,
                error_code=error_code,
                error_type=type(error).__name__,
                error_location=safe_exception_location(error),
                http_status=http_status,
                retryable=retryable,
                duration_ms=_elapsed_milliseconds(started_at_ns),
                attempt=1,
            )
            return self._failed(request, "RESEARCH_UNAVAILABLE")

        try:
            return self._map_response(
                request, response, provider_call_id, started_at_ns
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001, 不传播上游结构化响应异常
            self._record(
                "research_invocation_failed",
                DiagnosticLevel.ERROR,
                stage="response.map",
                provider_call_id=provider_call_id,
                error_code="RESPONSE_INVALID",
                error_type=type(error).__name__,
                error_location=safe_exception_location(error),
                retryable=False,
                duration_ms=_elapsed_milliseconds(started_at_ns),
                attempt=1,
            )
            return self._failed(request, "RESEARCH_UNAVAILABLE")

    def _map_response(
        self,
        request: ResearchRequest,
        response: object,
        provider_call_id: str,
        started_at_ns: int,
    ) -> ResearchResult:
        """把 SDK 响应映射为稳定研究契约。"""

        raw_usage = _field(response, "usage")
        usage = UsageSnapshot(
            int(_field(raw_usage, "input_tokens", 0) or 0),
            int(_field(raw_usage, "output_tokens", 0) or 0),
            int(_field(raw_usage, "cost_microunits", 0) or 0),
            True,
        )
        raw_sources = _field(response, "sources")
        if raw_sources is None:
            raw_sources = []
            for block in _field(response, "output", ()) or ():
                if _field(block, "type") == "web_search_call":
                    raw_sources.extend(_field(block, "sources", ()) or ())
                    raw_sources.extend(_field(block, "results", ()) or ())
        if not raw_sources:
            raw_sources = _sources_from_output_actions(
                _field(response, "output", ())
            )
        if not raw_sources:
            raw_sources = _sources_from_output_text(
                _field(response, "output_text", "")
            )
        observations: list[ResearchObservation] = []
        seen_urls: set[str] = set()
        invalid_seen = False
        rejected_count = 0
        for index, source in enumerate(tuple(raw_sources or ())[: request.max_sources]):
            try:
                url = normalize_evidence_url(str(_field(source, "url", "")))
                if url in seen_urls:
                    rejected_count += 1
                    continue
                title = str(_field(source, "title", ""))
                publisher = str(
                    _field(source, "publisher", _field(source, "site_name", ""))
                )
                conclusion_ids = frozenset(
                    _field(
                        source,
                        "supported_conclusion_ids",
                        request.expected_conclusion_ids,
                    )
                    or ()
                )
                if not conclusion_ids or not title.strip() or not publisher.strip():
                    invalid_seen = True
                    rejected_count += 1
                    continue
                seen_urls.add(url)
                observations.append(
                    ResearchObservation(
                        observation_id=str(
                            _field(
                                source,
                                "observation_id",
                                f"{request.request_id}-source-{index + 1}",
                            )
                        ),
                        title=title,
                        publisher=publisher,
                        source_url=url,
                        published_at_epoch_ms=_field(source, "published_at_epoch_ms"),
                        retrieved_at_epoch_ms=int(
                            _field(source, "retrieved_at_epoch_ms", 0) or 0
                        ),
                        source_scope=SourceScope.EXTERNAL_REFERENCE,
                        supported_conclusion_ids=conclusion_ids,
                        within_time_window=bool(
                            _field(source, "within_time_window", True)
                        ),
                        duplicate_status=EvidenceDuplicateStatus.UNIQUE,
                        quality_status=EvidenceQualityStatus.UNVERIFIED,
                    )
                )
            except (TypeError, ValueError, KeyError):
                invalid_seen = True
                rejected_count += 1
                continue
        if not observations:
            error_code = (
                "EVIDENCE_INVALID" if invalid_seen else "RESEARCH_INSUFFICIENT"
            )
            self._record(
                "research_evidence_insufficient",
                DiagnosticLevel.WARNING,
                stage="evidence.validate",
                provider_call_id=provider_call_id,
                error_code=error_code,
                retryable=False,
                duration_ms=_elapsed_milliseconds(started_at_ns),
                attempt=1,
                evidence_valid_count=0,
                evidence_rejected_count=rejected_count,
            )
            return self._failed(request, error_code, usage)
        self._record(
            "research_invocation_succeeded",
            DiagnosticLevel.INFO,
            stage="responses.create",
            provider_call_id=provider_call_id,
            duration_ms=_elapsed_milliseconds(started_at_ns),
            attempt=1,
            evidence_valid_count=len(observations),
            evidence_rejected_count=rejected_count,
        )
        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.SUCCEEDED,
            tuple(observations),
            (),
            None,
            usage,
        )

    def _record(
        self,
        event_name: str,
        level: DiagnosticLevel,
        *,
        stage: str,
        provider_call_id: str | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        error_location: str | None = None,
        http_status: int | None = None,
        retryable: bool | None = None,
        duration_ms: int | None = None,
        attempt: int | None = None,
        evidence_valid_count: int | None = None,
        evidence_rejected_count: int | None = None,
    ) -> None:
        """记录固定字段，并隔离诊断输出自身的故障。"""

        try:
            self.recorder.record(
                DiagnosticRecord(
                    event_name=event_name,
                    component="provider",
                    level=level,
                    capability="deepseek_web_search",
                    stage=stage,
                    provider="deepseek_web_search",
                    model=self.model,
                    provider_call_id=provider_call_id,
                    error_code=error_code,
                    error_type=error_type,
                    error_location=error_location,
                    http_status=http_status,
                    retryable=retryable,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    evidence_valid_count=evidence_valid_count,
                    evidence_rejected_count=evidence_rejected_count,
                )
            )
        except Exception:  # noqa: BLE001, 诊断不得影响研究结果
            return

    @staticmethod
    def _failed(
        request: ResearchRequest, code: str, usage: UsageSnapshot = _EMPTY_USAGE
    ) -> ResearchResult:
        return ResearchResult(
            "research-result/1",
            request.request_id,
            request.task_id,
            request.tenant_id,
            ResearchStatus.FAILED,
            (),
            (code,),
            code,
            usage,
        )


def _elapsed_milliseconds(started_at_ns: int) -> int:
    """以单调时钟生成不会倒退的调用耗时。"""

    return max(0, (time.monotonic_ns() - started_at_ns) // 1_000_000)


def _classify_invocation_error(error: Exception) -> tuple[str, bool, int | None]:
    """将上游异常压缩为稳定、无正文的研究诊断分类。"""

    http_status = _safe_http_status(error)
    if isinstance(error, (TimeoutError, APITimeoutError)) or http_status == 408:
        return "PROVIDER_TIMEOUT", True, http_status
    if http_status in {401, 403}:
        return "PROVIDER_AUTHENTICATION", False, http_status
    if http_status == 404:
        return "PROVIDER_NOT_FOUND", False, http_status
    if http_status == 429:
        return "PROVIDER_RATE_LIMITED", True, http_status
    if http_status is not None and 500 <= http_status <= 599:
        return "PROVIDER_UPSTREAM", True, http_status
    return "PROVIDER_UNAVAILABLE", True, http_status


def _safe_http_status(error: Exception) -> int | None:
    """仅接受异常公开整数状态，不读取异常正文或响应对象。"""

    status_code = getattr(error, "status_code", None)
    if (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 100 <= status_code <= 599
    ):
        return status_code
    return None


def _sources_from_output_text(value: object) -> tuple[dict[str, str], ...]:
    """从 Responses 正文中的公开链接恢复最小来源元数据。

    DeepSeek 当前部分响应只返回 `web_search_call` 和带链接的正文，SDK 的
    `sources` 字段可能为空。这里仅提取正文中明确出现的公开 URL，不访问 URL，
    不把正文内容写入诊断日志；标题与发布者只使用 URL 所在行的短标签。
    """

    if not isinstance(value, str) or not value.strip():
        return ()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"https?://[^\s<>\]\)\"']+", value):
        try:
            url = normalize_evidence_url(match.group(0).rstrip(".,;:，。；）】>"))
        except (TypeError, ValueError):
            continue
        if url in seen:
            continue
        seen.add(url)
        line_start = value.rfind("\n", 0, match.start()) + 1
        line = value[line_start : match.start()].strip()
        if not line:
            previous_lines = [
                item.strip()
                for item in value[:line_start].splitlines()
                if item.strip()
            ]
            line = previous_lines[-1] if previous_lines else ""
        line = re.sub(r"^[-*>\s]+", "", line).strip("* ")
        publisher, title = _source_label(line, url)
        results.append({"url": url, "title": title, "publisher": publisher})
    return tuple(results)


def _sources_from_output_actions(value: object) -> tuple[dict[str, str], ...]:
    """从 Responses API 的 ``web_search_call.open_page`` 动作恢复来源。"""

    if not isinstance(value, (tuple, list)):
        return ()
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if _field(item, "type") != "web_search_call":
            continue
        action = _field(item, "action")
        if _field(action, "type") != "open_page":
            continue
        raw_url = _field(action, "url")
        try:
            url = normalize_evidence_url(str(raw_url or ""))
        except (TypeError, ValueError):
            continue
        if url in seen:
            continue
        seen.add(url)
        hostname = urlparse(url).hostname or "公开来源"
        results.append({"url": url, "title": hostname, "publisher": hostname})
    return tuple(results)


def _source_label(line: str, url: str) -> tuple[str, str]:
    """把 URL 同行的来源标签压缩为标题和发布者。"""

    clean = re.sub(r"\s+", " ", line).strip()
    if clean:
        clean = re.sub(r"^(?:来源|出处)\s*[：:]\s*", "", clean)
        clean = clean.strip("* ")
    if "：" in clean or ":" in clean:
        separator = "：" if "：" in clean else ":"
        publisher, title = clean.split(separator, 1)
        publisher = re.sub(r"^[\s\-*>]+|[\s\-*>]+$", "", publisher)
        title = re.sub(r'^[\s\-*>" ]+|[\s\-*>" ]+$', "", title)
    else:
        publisher, title = "", re.sub(
            r'^[\s\-*>" ]+|[\s\-*>" ]+$', "", clean
        )
    hostname = urlparse(url).hostname or "公开来源"
    return publisher or hostname, title or hostname


__all__ = ["DeepSeekWebSearchProvider"]
