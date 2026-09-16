"""本地执行日志的字段白名单与组合根注册测试。"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from typing import cast

import httpx
import pytest
from pydantic import SecretStr

from efficiency_platform_agent.configuration.integration import S7IntegrationSettings
from efficiency_platform_agent.contracts.responses import (
    RunErrorV1,
    RunViewV1,
    UsageV1,
)
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    bind_diagnostic_context,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.core.runtime import RunEventRecord
from efficiency_platform_agent.observability.local_execution_log import (
    LocalExecutionLogger,
)


def test_diagnostic_log_contains_location_but_not_sensitive_values(caplog) -> None:
    """结构化诊断日志只能输出显式白名单字段。"""

    logger = logging.getLogger("tests.diagnostic_local_execution_log")
    caplog.set_level(logging.INFO, logger=logger.name)
    recorder = LocalExecutionLogger(logger=logger)
    sensitive_prompt = "Prompt-绝不能记录"
    synthetic_secret = "synthetic-secret-绝不能记录"

    with bind_diagnostic_context(run_id="run-a", request_id="request-a"):
        recorder.record(
            DiagnosticRecord(
                event_name="research_invocation_failed",
                component="provider",
                level=DiagnosticLevel.ERROR,
                stage="responses.create",
                error_code="PROVIDER_NOT_FOUND",
                error_type="NotFoundError",
                error_location="deepseek_web_search.py:42:search",
                http_status=404,
                retryable=False,
                duration_ms=312,
                attempt=1,
            )
        )

    text = "\n".join(caplog.messages)
    assert "[AgentProvider]" in text
    assert "事件=research_invocation_failed" in text
    assert "run_id=run-a request_id=request-a" in text
    assert "阶段=responses.create" in text
    assert "错误码=PROVIDER_NOT_FOUND" in text
    assert "异常类型=NotFoundError" in text
    assert "错误位置=deepseek_web_search.py:42:search" in text
    assert "HTTP状态=404" in text
    assert "可重试=false" in text
    assert "耗时毫秒=312 attempt=1" in text
    assert sensitive_prompt not in text
    assert synthetic_secret not in text


def test_record_rejects_sensitive_free_fields_before_logging(caplog) -> None:
    """record 路径不能把未知自由字段传入诊断记录。"""

    logger = logging.getLogger("tests.diagnostic_free_field")
    caplog.set_level(logging.INFO, logger=logger.name)
    recorder = LocalExecutionLogger(logger=logger)

    record = DiagnosticRecord(
        event_name="research_invocation_failed",
        component="provider",
        level=DiagnosticLevel.ERROR,
    )
    for field_name in ("message", "payload"):
        with pytest.raises(TypeError):
            recorder.record(  # type: ignore[call-arg]
                record,
                **{field_name: "合成密钥-绝不能记录"},
            )

    assert "合成密钥-绝不能记录" not in "\n".join(caplog.messages)


def test_recorder_failures_do_not_escape_to_callers() -> None:
    """底层 Logger 抛错时诊断记录器仍不得影响调用方。"""

    class _FailingLogger:
        """模拟任意日志写入均失败的受控 Logger。"""

        def log(self, *args: object, **kwargs: object) -> None:
            """模拟写入诊断日志失败。"""

            del args, kwargs
            raise RuntimeError("日志写入失败")

        def info(self, *args: object, **kwargs: object) -> None:
            """模拟写入能力日志失败。"""

            del args, kwargs
            raise RuntimeError("日志写入失败")

    recorder = LocalExecutionLogger(logger=cast(logging.Logger, _FailingLogger()))

    recorder.record(
        DiagnosticRecord(
            event_name="research_invocation_started",
            component="provider",
            level=DiagnosticLevel.INFO,
        )
    )
    recorder.log_capability("deepseek_web_search", enabled=False)


def test_capability_log_uses_fixed_fields_without_free_event_input(caplog) -> None:
    """能力日志只根据启用状态推导固定事件，不接收自由事件名。"""

    logger = logging.getLogger("tests.capability_local_execution_log")
    caplog.set_level(logging.INFO, logger=logger.name)
    recorder = LocalExecutionLogger(logger=logger)

    recorder.log_capability(
        "deepseek_web_search",
        enabled=False,
        reason_code="gate_disabled",
    )

    assert caplog.messages == [
        (
            "[AgentCapability] 事件=capability_disabled 能力=deepseek_web_search "
            "状态=disabled 原因码=gate_disabled"
        )
    ]
    with pytest.raises(ValueError):
        recorder.log_capability(
            "deepseek_web_search",
            enabled=True,
            reason_code="gate_disabled",
        )


def test_default_logger_remains_visible_after_uvicorn_logging_configuration() -> None:
    """Uvicorn 配置后 INFO 日志仍须由独立且不重复的 Handler 输出。"""

    script = textwrap.dedent(
        """
        import asyncio
        import logging
        import logging.config
        from copy import deepcopy

        from uvicorn.config import LOGGING_CONFIG

        from efficiency_platform_agent.core.enums import RunStatus
        from efficiency_platform_agent.core.run import JsonObject
        from efficiency_platform_agent.core.runtime import RunEventRecord
        from efficiency_platform_agent.observability.local_execution_log import LocalExecutionLogger

        execution_logger = LocalExecutionLogger()
        logging.config.dictConfig(deepcopy(LOGGING_CONFIG))
        LocalExecutionLogger()
        logger = logging.getLogger("efficiency_platform_agent.execution")
        uvicorn_handlers = {
            handler
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
            for handler in logging.getLogger(name).handlers
        }
        shared = any(
            handler in logging.getLogger().handlers or handler in uvicorn_handlers
            for handler in logger.handlers
        )
        print(
            f"level={logger.level} effective={logger.getEffectiveLevel()} "
            f"handlers={len(logger.handlers)} propagate={logger.propagate} shared={shared}"
        )
        event = RunEventRecord(
            "event-visible",
            "run_started",
            "run-visible",
            "tenant-hidden",
            1,
            1,
            RunStatus.RUNNING,
            JsonObject(),
        )
        asyncio.run(execution_logger.on_run_event(event))
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (
        "level=20 effective=20 handlers=1 propagate=False shared=False"
        in completed.stdout
    )
    assert (
        "INFO [AgentRun] 事件=run_started run_id=run-visible 状态=running"
        in completed.stderr
    )
    assert "tenant-hidden" not in completed.stderr


@pytest.mark.asyncio
async def test_logger_emits_only_allowed_event_and_terminal_fields(caplog) -> None:
    """日志必须保留运行摘要，同时完全忽略所有正文载荷。"""

    logger = logging.getLogger("tests.local_execution_log")
    caplog.set_level(logging.INFO, logger=logger.name)
    execution_logger = LocalExecutionLogger(logger=logger)
    forbidden_values = (
        "用户正文-绝不能记录",
        "Prompt-绝不能记录",
        "模型输出-绝不能记录",
        "Authorization: Bearer secret-token",
        "postgresql://user:password@host/database",
        "Traceback (most recent call last)",
    )
    event = RunEventRecord(
        event_id="event-sensitive",
        event_type="run_started",
        run_id="run-sensitive",
        tenant_id="tenant-sensitive",
        sequence=1,
        occurred_at_epoch_ms=1,
        status=RunStatus.RUNNING,
        payload=JsonObject(
            tuple((f"field_{index}", value) for index, value in enumerate(forbidden_values))
        ),
    )
    view = RunViewV1(
        run_id="run-sensitive",
        request_id="request-sensitive",
        status=RunStatus.FAILED,
        strategy=StrategyMode.MULTI_AGENT,
        output={"content": forbidden_values[2]},
        error=RunErrorV1(
            code="MODEL_FAILED",
            category="runtime",
            retryable=False,
            safe_message=forbidden_values[0],
        ),
        usage=UsageV1(
            input_tokens=11,
            output_tokens=7,
            cost_microunits=3,
            estimated=False,
        ),
        degraded=True,
    )

    await execution_logger.on_run_event(event)
    await execution_logger.on_run_state(view)

    text = "\n".join(caplog.messages)
    assert "事件=run_started run_id=run-sensitive 状态=running" in text
    assert (
        "事件=run_failed run_id=run-sensitive request_id=request-sensitive "
        "状态=failed 策略=multi_agent 错误码=MODEL_FAILED 降级=true "
        "输入Token=11 输出Token=7"
    ) in text
    for forbidden in forbidden_values:
        assert forbidden not in text
    assert "tenant-sensitive" not in text


@pytest.mark.asyncio
async def test_real_composition_root_registers_local_execution_logger(monkeypatch) -> None:
    """真实组合根必须显式登记事件与终态日志监听器。"""

    from efficiency_platform_agent.harness import local_real_factory

    class _RecordingExecutionLogger:
        """提供可识别的绑定方法，避免测试依赖真实日志输出。"""

        def __init__(self) -> None:
            self.records: list[DiagnosticRecord] = []
            self.capabilities: list[tuple[str, bool, str | None]] = []

        def record(self, record: DiagnosticRecord) -> None:
            """记录组合根产生的诊断记录。"""

            self.records.append(record)

        def log_capability(
            self,
            capability: str,
            *,
            enabled: bool,
            reason_code: str | None = None,
        ) -> None:
            """记录组合根产生的能力状态。"""

            self.capabilities.append((capability, enabled, reason_code))

        async def on_run_event(self, event) -> None:
            del event

        async def on_run_state(self, view) -> None:
            del view

    execution_logger = _RecordingExecutionLogger()
    monkeypatch.setattr(
        local_real_factory, "LocalExecutionLogger", lambda: execution_logger
    )
    settings = S7IntegrationSettings(
        deepseek_base_url=SecretStr("https://synthetic.invalid"),
        deepseek_api_key=SecretStr("synthetic-key"),
        deepseek_fast_model=SecretStr("synthetic-fast"),
        deepseek_balanced_model=SecretStr("synthetic-balanced"),
        deepseek_strong_model=SecretStr("synthetic-strong"),
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, request=request)
        )
    )

    bundle = local_real_factory.build_local_agent_application(
        settings,
        http_client=client,
    )
    try:
        assert any(
            getattr(listener, "__self__", None) is execution_logger
            for listener in bundle.runtime._run_event_listeners
        )
        assert any(
            getattr(listener, "__self__", None) is execution_logger
            for listener in bundle.runtime._run_state_listeners
        )
        assert execution_logger.capabilities == [
            ("deepseek_chat", True, None),
            ("deepseek_web_search", False, "RESEARCH_GATE_DISABLED"),
        ]
    finally:
        await bundle.close()
        await client.aclose()


@pytest.mark.asyncio
async def test_test_mode_does_not_register_local_execution_logger(monkeypatch) -> None:
    """显式测试模式不得隐式创建本地终端日志器。"""

    from efficiency_platform_agent.harness import local_real_factory

    def reject_logger_creation():
        raise AssertionError("测试模式不应创建本地执行日志器")

    monkeypatch.setattr(
        local_real_factory, "LocalExecutionLogger", reject_logger_creation
    )
    settings = S7IntegrationSettings(
        deepseek_base_url=SecretStr("https://synthetic.invalid"),
        deepseek_api_key=SecretStr("synthetic-key"),
        deepseek_fast_model=SecretStr("synthetic-fast"),
        deepseek_balanced_model=SecretStr("synthetic-balanced"),
        deepseek_strong_model=SecretStr("synthetic-strong"),
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, request=request)
        )
    )

    bundle = local_real_factory.build_local_agent_application(
        settings,
        test_mode=True,
        http_client=client,
    )
    try:
        assert bundle.runtime._run_event_listeners == []
    finally:
        await bundle.close()
        await client.aclose()
