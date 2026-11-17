"""问题预算作用域由服务端生成，后台子任务继承同一ContextVar。"""

from uuid import uuid4

from starlette.types import ASGIApp, Receive, Scope, Send

from efficiency_platform_agent.core.paid_budget import paid_scope


class PaidBudgetScopeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # 不读取客户端的预算ID/金额/作用域，防止业务输入自行领取新额度。
        with paid_scope("http-" + uuid4().hex):
            await self.app(scope, receive, send)
