"""仅本机真实生命周期IT的调度握手；模型仍complete-only Fake，其余沿生产组合。"""
import asyncio
import os
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from efficiency_platform_agent.api import routes
from efficiency_platform_agent.core.context_dispatch import current_model_stage
from efficiency_platform_agent.core.run_context_binding import current_run_context
from tests.integration.context_control import private_memory_http_fixture as base


@dataclass
class Gates:
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_seen: asyncio.Event = field(default_factory=asyncio.Event)
    exit_release: asyncio.Event = field(default_factory=asyncio.Event)
    exited: asyncio.Event = field(default_factory=asyncio.Event)
    reader_open: asyncio.Event = field(default_factory=asyncio.Event)
    reader_release: asyncio.Event = field(default_factory=asyncio.Event)
    runtime_id: str = ""
    execution_id: str = ""
    tenant_id: str = ""
    provider_calls: int = 0
    direct_calls: int = 0
    application: object = None


gates = Gates()
_create_app = base.create_app
_stream_run_events = routes.stream_run_events


class HeldBoundary(base.FixedBoundary):
    async def complete(self, request):
        gates.provider_calls += 1
        stage = current_model_stage()
        if stage is None or stage.node_id != "direct":
            return await super().complete(request)
        gates.direct_calls += 1
        if gates.direct_calls != 1:
            raise ValueError("MEMORY_IT_UNEXPECTED_PROVIDER_RETRY")
        binding = current_run_context()
        runtime = gates.application.state.runtime_service
        record = await runtime.memory_execution_store.get(binding.conversation.tenant_id, binding.execution_id)
        gates.tenant_id, gates.execution_id, gates.runtime_id = binding.conversation.tenant_id, binding.execution_id, record.runtime_id
        gates.entered.set()
        try:
            # 观察真实owner取消信号，阻塞协作退出以验证STOP不能提前ACK。
            await runtime._wait_cancelled(record.runtime_id)
            gates.cancel_seen.set()
            await gates.exit_release.wait()
            raise asyncio.CancelledError
        finally:
            gates.exited.set()


class RestartSeedRepository(base.MySqlReleaseRepository):
    async def save(self, release_id, bundle):
        existing = await self.get(release_id)
        if existing is not None:
            if existing.snapshot_checksum != bundle.snapshot_checksum:
                raise ValueError("MEMORY_IT_RELEASE_SEED_CONFLICT")
            return existing
        return await super().save(release_id, bundle)


async def held_stream(event_hub, run_id, **kwargs):
    original = _stream_run_events(event_hub, run_id, **kwargs)
    try:
        first = True
        async for chunk in original:
            yield chunk
            if first and run_id == gates.runtime_id:
                first = False
                gates.reader_open.set()
                # 只控制真实SSE生成器的下一次调度，不改变其授权或输出逻辑。
                await gates.reader_release.wait()
    finally:
        await original.aclose()


def create_app(*args, **kwargs):
    app = _create_app(*args, **kwargs)
    gates.application = app
    secret = os.environ["MEMORY_IT_INTERNAL_SECRET"]

    def authorized(request):
        if os.environ.get("MEMORY_IT_ENABLED") != "1" or request.client is None or request.client.host not in {"127.0.0.1", "::1"} or request.headers.get("Authorization") != "Bearer " + secret:
            raise HTTPException(401, detail="MEMORY_IT_INTERNAL_ONLY")

    @app.get("/__memory_it__/inflight/wait/{phase}")
    async def wait_phase(phase: str, request: Request):
        authorized(request)
        event = {"entered": gates.entered, "cancel_seen": gates.cancel_seen, "reader_open": gates.reader_open, "exited": gates.exited}.get(phase)
        if event is None:
            raise HTTPException(404)
        try:
            async with asyncio.timeout(8):
                await event.wait()
        except TimeoutError:
            raise HTTPException(504, detail="MEMORY_IT_GATE_TIMEOUT") from None
        return {"observed": True, "runtime_id": gates.runtime_id, "execution_id": gates.execution_id, "provider_calls": gates.provider_calls, "direct_calls": gates.direct_calls}

    @app.post("/__memory_it__/inflight/{action}")
    async def action(action: str, request: Request):
        authorized(request)
        runtime = app.state.runtime_service
        if action == "seed-buffer":
            if not gates.entered.is_set() or gates.cancel_seen.is_set():
                raise HTTPException(409)
            accepted = await runtime.publish_assistant_delta(gates.runtime_id, "synthetic-inflight-private-marker")
            return {"accepted": accepted}
        if action == "release-exit":
            gates.exit_release.set()
            return {"released": True}
        if action == "release-reader":
            gates.reader_release.set()
            return {"released": True}
        if action == "late-publish":
            try:
                accepted = await runtime.publish_assistant_delta(gates.runtime_id, "synthetic-inflight-private-marker")
            except ValueError:
                accepted = False
            return {"accepted": accepted, "provider_calls": gates.provider_calls, "direct_calls": gates.direct_calls}
        raise HTTPException(404)

    @app.get("/__memory_it__/inflight/authority/{execution_id}")
    async def authority(execution_id: str, request: Request):
        authorized(request)
        tenant = request.headers.get("X-Tenant-ID")
        if not tenant:
            raise HTTPException(400)
        try:
            record = await app.state.runtime_service.memory_execution_store.get(tenant, execution_id)
        except ValueError as error:
            if str(error) == "MEMORY_ACCESS_REVOKED":
                return {"revoked": True, "provider_calls": gates.provider_calls}
            raise HTTPException(503, detail="MEMORY_IT_AUTHORITY_UNAVAILABLE") from None
        return {"revoked": record is not None and record.state != "ACTIVE", "provider_calls": gates.provider_calls}

    return app


async def main():
    if os.environ.get("MEMORY_IT_ENABLED") != "1":
        raise ValueError("MEMORY_IT_LOCAL_ONLY")
    base.FixedBoundary = HeldBoundary
    base.MySqlReleaseRepository = RestartSeedRepository
    base.create_app = create_app
    routes.stream_run_events = held_stream
    await base.main()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
