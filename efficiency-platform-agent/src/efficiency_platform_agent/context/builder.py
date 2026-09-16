"""唯一的最小 Context Builder 实现。"""

from __future__ import annotations

from efficiency_platform_agent.context.contracts import (
    BuiltContext,
    ContextSource,
    TrustLevel,
)
from efficiency_platform_agent.core.run import ExecutionBudget, RunContext, RunRequest


class ContextBuildError(ValueError):
    """不回显输入正文的稳定 Context 构建错误。"""

    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


class ContextBuilder:
    """装配身份一致且预算受限的最小上下文。"""

    def build(
        self,
        request: RunRequest,
        run_context: RunContext,
        budget: ExecutionBudget,
        allowed_tools: frozenset[str],
    ) -> BuiltContext:
        """只装配用户输入，不读取其他上下文来源。"""
        if not isinstance(request, RunRequest):
            raise TypeError("request 必须是 RunRequest")
        if not isinstance(run_context, RunContext):
            raise TypeError("run_context 必须是 RunContext")
        if not isinstance(budget, ExecutionBudget):
            raise TypeError("budget 必须是 ExecutionBudget")
        if not isinstance(allowed_tools, frozenset):
            raise TypeError("allowed_tools 必须是 frozenset")
        if (
            request.tenant_id != run_context.tenant_id
            or request.user_id != run_context.user_id
        ):
            raise ContextBuildError("CONTEXT_IDENTITY_MISMATCH", "Context 身份校验失败")

        estimated = (len(request.input_text) + 3) // 4
        if estimated > budget.max_input_tokens:
            raise ContextBuildError("CONTEXT_BUDGET_EXCEEDED", "Context 输入预算不足")

        source = ContextSource(
            source_id="user_input",
            trust_level=TrustLevel.USER_UNTRUSTED,
            content=request.input_text,
        )
        return BuiltContext(
            run_id=run_context.run_id,
            tenant_id=run_context.tenant_id,
            user_id=run_context.user_id,
            sources=(source,),
            allowed_tools=allowed_tools,
            max_input_tokens=budget.max_input_tokens,
            estimated_input_tokens=estimated,
        )
