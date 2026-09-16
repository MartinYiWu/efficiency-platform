"""诊断契约与 Run 上下文的单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    NoopDiagnosticRecorder,
    RunDiagnosticContext,
    bind_diagnostic_context,
    current_diagnostic_context,
    safe_exception_location,
)


def test_context_binding_is_nested_and_restored() -> None:
    """嵌套绑定结束后必须恢复上层和默认上下文。"""

    assert current_diagnostic_context() == RunDiagnosticContext()


def test_context_binding_is_isolated_between_concurrent_tasks() -> None:
    """并发任务绑定的 Run 上下文不得相互串线。"""

    async def read_context(run_id: str) -> RunDiagnosticContext:
        with bind_diagnostic_context(run_id=run_id):
            await asyncio.sleep(0)
            return current_diagnostic_context()

    async def collect_contexts() -> list[RunDiagnosticContext]:
        return await asyncio.gather(read_context("run-a"), read_context("run-b"))

    contexts = asyncio.run(collect_contexts())

    assert contexts == [
        RunDiagnosticContext(run_id="run-a"),
        RunDiagnosticContext(run_id="run-b"),
    ]
    with bind_diagnostic_context(run_id="run-a", request_id="request-a"):
        assert current_diagnostic_context().run_id == "run-a"
        with bind_diagnostic_context(strategy="multi_agent"):
            assert current_diagnostic_context().strategy == "multi_agent"
        assert current_diagnostic_context().strategy is None
    assert current_diagnostic_context() == RunDiagnosticContext()


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("event_name", ""),
        ("component", ""),
        ("duration_ms", -1),
        ("attempt", -1),
        ("input_tokens", -1),
        ("output_tokens", -1),
        ("evidence_valid_count", -1),
        ("evidence_rejected_count", -1),
        ("http_status", 99),
        ("http_status", 600),
        ("provider_call_id", "provider call id with spaces"),
    ),
)
def test_diagnostic_record_rejects_invalid_explicit_values(
    field_name: str, value: object
) -> None:
    """诊断契约必须拒绝空标识、负耗时和非法 HTTP 状态。"""

    fields: dict[str, object] = {
        "event_name": "research_invocation_failed",
        "component": "provider",
        "level": DiagnosticLevel.ERROR,
    }
    fields[field_name] = value

    with pytest.raises(ValueError):
        DiagnosticRecord(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field_name",
    (
        "http_status",
        "duration_ms",
        "attempt",
        "input_tokens",
        "output_tokens",
        "evidence_valid_count",
        "evidence_rejected_count",
    ),
)
@pytest.mark.parametrize("value", (1.5, "1", float("nan")))
def test_diagnostic_record_rejects_non_integer_numeric_values(
    field_name: str, value: object
) -> None:
    """数值字段必须拒绝浮点、字符串和非数值 NaN。"""

    fields: dict[str, object] = {
        "event_name": "research_invocation_failed",
        "component": "provider",
        "level": DiagnosticLevel.ERROR,
    }
    fields[field_name] = value

    with pytest.raises(ValueError):
        DiagnosticRecord(**fields)  # type: ignore[arg-type]


def test_diagnostic_record_rejects_fractional_http_status_in_valid_range() -> None:
    """HTTP 状态即使处于数值范围内也必须是整数。"""

    with pytest.raises(ValueError):
        DiagnosticRecord(
            event_name="research_invocation_failed",
            component="provider",
            level=DiagnosticLevel.ERROR,
            http_status=200.5,  # type: ignore[arg-type]
        )


def test_diagnostic_record_accepts_only_explicit_whitelist_fields() -> None:
    """诊断记录应保留设计定义的白名单字段。"""

    record = DiagnosticRecord(
        event_name="research_evidence_validated",
        component="provider",
        level=DiagnosticLevel.INFO,
        capability="deepseek_web_search",
        status="succeeded",
        stage="responses.create",
        provider="deepseek",
        model="deepseek-chat",
        provider_call_id="call-1_a.2",
        reason_code="evidence_valid",
        rule_version="2026-09-08",
        error_code="EVIDENCE_INVALID",
        error_type="ValueError",
        error_location="deepseek_web_search.py:42:search",
        http_status=200,
        retryable=False,
        duration_ms=1,
        attempt=0,
        input_tokens=2,
        output_tokens=3,
        evidence_valid_count=4,
        evidence_rejected_count=5,
    )

    assert record.provider_call_id == "call-1_a.2"
    assert record.evidence_rejected_count == 5


def test_diagnostic_record_rejects_unapproved_payload_field() -> None:
    """诊断记录不能接收自由载荷字段。"""

    with pytest.raises(TypeError):
        DiagnosticRecord(
            event_name="research_invocation_failed",
            component="provider",
            level=DiagnosticLevel.ERROR,
            payload="合成密钥-绝不能接受",  # type: ignore[call-arg]
        )


def test_noop_diagnostic_recorder_discards_record() -> None:
    """默认 Recorder 必须同步丢弃记录且不影响业务链。"""

    recorder = NoopDiagnosticRecorder()

    assert (
        recorder.record(
            DiagnosticRecord(
                event_name="research_invocation_started",
                component="provider",
                level=DiagnosticLevel.INFO,
            )
        )
        is None
    )


def test_safe_exception_location_returns_last_project_frame_without_message() -> None:
    """异常位置只包含项目内最后一帧的位置，不包含异常正文。"""

    try:
        raise RuntimeError("合成密钥-绝不能记录")
    except RuntimeError as error:
        location = safe_exception_location(error)

    assert location is not None
    assert location.startswith("test_diagnostics.py:")
    assert location.endswith(":test_safe_exception_location_returns_last_project_frame_without_message")
    assert "合成密钥-绝不能记录" not in location
