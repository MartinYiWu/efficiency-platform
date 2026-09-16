"""基于显式注册信息的确定性策略路由。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..core.enums import StrategyMode


class _StrategyRequest(Protocol):
    """策略路由所需的最小请求视图。"""

    requested_strategy: StrategyMode | None
    workflow_id: str | None


@dataclass(frozen=True, slots=True)
class StrategySelection:
    """一次路由产生的不可变策略选择事实。"""

    mode: StrategyMode
    rule_version: str
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.mode, StrategyMode):
            raise TypeError("mode 必须是 StrategyMode")
        if not isinstance(self.rule_version, str) or not self.rule_version.strip():
            raise ValueError("rule_version 不能为空")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code 不能为空")


class StrategyRoutingError(ValueError):
    """策略路由失败的安全错误，不携带请求正文。"""

    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class StrategyRouter:
    """只依据模式和显式注册表选择策略，不执行任何运行时能力。"""

    RULE_VERSION = "s2.strategy/1"

    def __init__(
        self,
        available_modes: frozenset[StrategyMode],
        *,
        registered_workflow_ids: frozenset[str] = frozenset(),
    ) -> None:
        if not isinstance(available_modes, frozenset):
            raise TypeError("available_modes 必须是 frozenset")
        if any(not isinstance(mode, StrategyMode) for mode in available_modes):
            raise TypeError("available_modes 只能包含 StrategyMode")
        if not isinstance(registered_workflow_ids, frozenset):
            raise TypeError("registered_workflow_ids 必须是 frozenset")
        if any(
            not isinstance(workflow_id, str) or not workflow_id.strip()
            for workflow_id in registered_workflow_ids
        ):
            raise ValueError("registered_workflow_ids 只能包含非空字符串")
        self._available_modes = available_modes
        self._registered_workflow_ids = registered_workflow_ids

    def select(self, request: _StrategyRequest) -> StrategySelection:
        """按冻结规则返回选择；失败时在任何执行副作用前抛出安全错误。"""
        if request is None:
            raise StrategyRoutingError("INVALID_REQUEST", "策略请求无效")
        try:
            requested = request.requested_strategy
            workflow_id = request.workflow_id
        except AttributeError as error:
            raise StrategyRoutingError("INVALID_REQUEST", "策略请求无效") from error

        if requested is not None and not isinstance(requested, StrategyMode):
            raise StrategyRoutingError("INVALID_REQUEST", "策略请求无效")
        if workflow_id is not None and (
            not isinstance(workflow_id, str) or not workflow_id.strip()
        ):
            raise StrategyRoutingError("INVALID_REQUEST", "工作流标识无效")

        if workflow_id is not None and requested in {
            None,
            StrategyMode.WORKFLOW,
        }:
            self._require_mode(StrategyMode.WORKFLOW)
            if workflow_id not in self._registered_workflow_ids:
                raise StrategyRoutingError("WORKFLOW_NOT_REGISTERED", "工作流未注册")
            return StrategySelection(
                mode=StrategyMode.WORKFLOW,
                rule_version=self.RULE_VERSION,
                reason_code="explicit_workflow",
            )

        if workflow_id is None and requested in {None, StrategyMode.DIRECT}:
            self._require_mode(StrategyMode.DIRECT)
            return StrategySelection(
                mode=StrategyMode.DIRECT,
                rule_version=self.RULE_VERSION,
                reason_code="simple_no_tool",
            )

        if requested in {
            StrategyMode.REACT,
            StrategyMode.PLAN_EXECUTE,
            StrategyMode.MULTI_AGENT,
        }:
            if workflow_id is not None:
                raise StrategyRoutingError(
                    "STRATEGY_INPUT_CONFLICT", "策略与工作流输入冲突"
                )
            if requested not in self._available_modes:
                raise StrategyRoutingError(
                    "STRATEGY_NOT_AVAILABLE_IN_S2", "请求的策略当前未注册"
                )
            return StrategySelection(
                mode=requested,
                rule_version=self.RULE_VERSION,
                reason_code="registered_requested_strategy",
            )

        raise StrategyRoutingError("STRATEGY_INPUT_CONFLICT", "策略输入冲突")

    def _require_mode(self, mode: StrategyMode) -> None:
        """确保组合根显式注册了目标模式。"""
        if mode not in self._available_modes:
            raise StrategyRoutingError(
                "STRATEGY_NOT_AVAILABLE_IN_S2", "请求的策略当前未注册"
            )


__all__ = ["StrategyRouter", "StrategyRoutingError", "StrategySelection"]
