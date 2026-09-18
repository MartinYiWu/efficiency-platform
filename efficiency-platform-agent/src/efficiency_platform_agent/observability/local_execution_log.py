"""面向本地开发终端的受控 Run 执行日志。"""

from __future__ import annotations

import logging
from contextlib import suppress

from efficiency_platform_agent.contracts.responses import RunViewV1
from efficiency_platform_agent.core.diagnostics import (
    DiagnosticLevel,
    DiagnosticRecord,
    current_diagnostic_context,
)
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.runtime import RunEventRecord


class _LocalExecutionHandler(logging.StreamHandler):
    """标识由本地执行日志器独占管理的终端 Handler。"""


def _default_logger() -> logging.Logger:
    """配置不依赖 root 或 Uvicorn Logger 的本地终端输出。"""
    logger = logging.getLogger("efficiency_platform_agent.execution")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.disabled = False
    if not any(isinstance(handler, _LocalExecutionHandler) for handler in logger.handlers):
        handler = _LocalExecutionHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


class LocalExecutionLogger:
    """仅按固定白名单输出生命周期事件与终态摘要。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _default_logger()

    def record(self, record: DiagnosticRecord) -> None:
        """以固定白名单字段记录诊断事实，并隔离日志器自身异常。"""

        with suppress(Exception):
            self._logger.log(
                _diagnostic_logging_level(record.level),
                "%s",
                _format_diagnostic_record(record),
            )

    def log_capability(
        self,
        capability: str,
        *,
        enabled: bool,
        reason_code: str | None = None,
    ) -> None:
        """记录能力启用或关闭状态，不输出配置原值。"""

        if enabled and reason_code is not None:
            raise ValueError("启用的能力不能携带原因码")
        event_name = "capability_ready" if enabled else "capability_disabled"
        status = "enabled" if enabled else "disabled"
        fields = [
            "[AgentCapability]",
            f"事件={event_name}",
            f"能力={capability}",
            f"状态={status}",
        ]
        if reason_code is not None:
            fields.append(f"原因码={reason_code}")
        with suppress(Exception):
            self._logger.info("%s", " ".join(fields))

    async def on_run_event(self, event: RunEventRecord) -> None:
        """记录已持久化事件，不读取可能携带正文的事件载荷。"""
        self._logger.info(
            "[AgentRun] 事件=%s run_id=%s 状态=%s",
            event.event_type,
            event.run_id,
            event.status.value,
        )

    async def on_run_state(self, view: RunViewV1) -> None:
        """记录终态安全视图中的策略、错误码、降级和 Token 汇总。"""
        error_code = view.error.code if view.error is not None else "-"
        strategy = view.strategy.value if view.strategy is not None else "-"
        level = self._terminal_level(view)
        self._logger.log(
            level,
            (
                "[AgentRun] 事件=run_%s run_id=%s request_id=%s 状态=%s "
                "策略=%s 错误码=%s 降级=%s 输入Token=%d 输出Token=%d"
            ),
            view.status.value,
            view.run_id,
            view.request_id,
            view.status.value,
            strategy,
            error_code,
            str(view.degraded).lower(),
            view.usage.input_tokens,
            view.usage.output_tokens,
        )

    @staticmethod
    def _terminal_level(view: RunViewV1) -> int:
        """按终态结果选择日志级别，不读取错误正文。"""
        if view.status in {RunStatus.FAILED, RunStatus.TIMED_OUT}:
            return logging.ERROR
        if view.degraded:
            return logging.WARNING
        return logging.INFO


_COMPONENT_PREFIXES = {
    "run": "AgentRun",
    "model": "AgentModel",
    "provider": "AgentProvider",
    "graph": "AgentGraph",
    "scheduler": "AgentScheduler",
}


def _diagnostic_logging_level(level: DiagnosticLevel) -> int:
    """把受控诊断级别转换为标准库日志级别。"""

    return {
        DiagnosticLevel.DEBUG: logging.DEBUG,
        DiagnosticLevel.INFO: logging.INFO,
        DiagnosticLevel.WARNING: logging.WARNING,
        DiagnosticLevel.ERROR: logging.ERROR,
    }[level]


def _format_diagnostic_record(record: DiagnosticRecord) -> str:
    """按固定顺序渲染诊断记录，不遍历任意映射或载荷。"""

    prefix = _COMPONENT_PREFIXES.get(record.component)
    if prefix is None:
        raise ValueError("component 不支持本地诊断日志")
    context = current_diagnostic_context()
    fields = [f"[Agent{prefix.removeprefix('Agent')}]", f"事件={record.event_name}"]
    _append_if_present(fields, "run_id", context.run_id)
    _append_if_present(fields, "request_id", context.request_id)
    _append_if_present(fields, "策略", context.strategy)
    _append_if_present(fields, "Agent", context.agent_name)
    _append_if_present(fields, "能力", record.capability)
    _append_if_present(fields, "状态", record.status)
    _append_if_present(fields, "阶段", record.stage)
    _append_if_present(fields, "provider", record.provider)
    _append_if_present(fields, "模型", record.model)
    _append_if_present(fields, "调用ID", record.provider_call_id)
    _append_if_present(fields, "原因码", record.reason_code)
    _append_if_present(fields, "规则版本", record.rule_version)
    _append_if_present(fields, "错误码", record.error_code)
    _append_if_present(fields, "异常类型", record.error_type)
    _append_if_present(fields, "错误位置", record.error_location)
    _append_if_present(fields, "HTTP状态", record.http_status)
    _append_if_present(fields, "可重试", _lowercase_boolean(record.retryable))
    _append_if_present(fields, "耗时毫秒", record.duration_ms)
    _append_if_present(fields, "attempt", record.attempt)
    _append_if_present(fields, "输入Token", record.input_tokens)
    _append_if_present(fields, "输出Token", record.output_tokens)
    _append_if_present(fields, "有效证据数", record.evidence_valid_count)
    _append_if_present(fields, "拒绝证据数", record.evidence_rejected_count)
    return " ".join(fields)


def _append_if_present(fields: list[str], key: str, value: object | None) -> None:
    """仅追加非空的白名单字段。"""

    if value is not None:
        fields.append(f"{key}={value}")


def _lowercase_boolean(value: bool | None) -> str | None:
    """把布尔值渲染为稳定的小写文本。"""

    if value is None:
        return None
    return str(value).lower()


__all__ = ["LocalExecutionLogger"]
