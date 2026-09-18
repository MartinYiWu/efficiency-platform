"""本地工具组合的权限、网络与预算离线回归。"""

import asyncio
import gzip
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module, util
from pathlib import Path

import pytest

from efficiency_platform_agent.configuration.research_local_sources import (
    load_local_source_descriptors,
)
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_execution import bind_budget_execution
from efficiency_platform_agent.core.run import JsonObject, RunContext, ToolRequest
from efficiency_platform_agent.harness.research_local_runtime import (
    build_local_research_binding,
)
from efficiency_platform_agent.providers.research.transport import PinnedResponse
from efficiency_platform_agent.tools.external.research import _freeze, _thaw
from efficiency_platform_agent.tools.runtime.service import ToolLeaseContext

NOW = datetime(2026, 9, 17, 14, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]
REMAINING = RemainingBudget(50, 60, 1000, 1000, 1000, 180_000)


def module():
    name = "efficiency_platform_agent.harness.research_local_tools"
    assert util.find_spec(name) is not None, "LOCAL_RESEARCH_TOOLS_MISSING"
    return import_module(name)


def source(source_id="google_blog_rss", *, body=False):
    item = next(
        x
        for x in load_local_source_descriptors(
            ROOT / "config/research_local_live_sources.toml"
        )
        if x.source_id == source_id
    )
    uses = (
        (
            "research",
            "platform_text" if source_id == "hacker_news_api" else "article_body",
        )
        if body
        else ("research",)
    )
    return item.model_copy(
        update={
            "enabled": True,
            "content_endpoints": (
                ("https://hacker-news.firebaseio.com/v0/item/123.json",)
                if source_id == "hacker_news_api"
                else ("https://blog.google/article", "https://blog.google/second")
            )
            if body
            else (),
            "history_mode": "unknown",
            "admission": item.admission.model_copy(
                update={
                    "intended_uses": uses,
                    "reason_codes": () if body else item.admission.reason_codes,
                }
            ),
            "content_policy": item.content_policy.model_copy(
                update={"storage_mode": "excerpt_only"}
            ),
            "rate_policy": item.rate_policy.model_copy(
                update={"requests": 100, "period_seconds": 1}
            ),
        }
    )


class Connector:
    supports_ip_pinning = True
    supports_tls_server_name = True
    verifies_certificates = True
    uses_environment_proxy = False

    def __init__(self, responses=None):
        self.responses = list(
            responses
            or [
                PinnedResponse(
                    200,
                    {"content-type": "text/plain"},
                    (b"Original verified article body.",),
                )
            ]
        )
        self.calls = []

    async def request(self, target, **kwargs):
        self.calls.append(target)
        return self.responses.pop(0)


class Resolver:
    def __init__(self, addresses=None):
        self.addresses = list(addresses or [("8.8.8.8",)])
        self.calls = []

    async def resolve(self, host, port):
        self.calls.append((host, port))
        return self.addresses[min(len(self.calls) - 1, len(self.addresses) - 1)]


@pytest.mark.asyncio
async def test_body_http_quota_counts_each_redirect_before_socket_dispatch():
    redirects = [
        response
        for _ in range(16)
        for response in (
            PinnedResponse(302, {"location": "https://blog.google/second"}, (b"hop",)),
            PinnedResponse(200, {"content-type": "text/plain"}, (b"body",)),
        )
    ]
    case = setup(
        descriptors=(source(body=True), source("hacker_news_api", body=True)),
        connector=Connector(redirects),
    )
    results = [await invoke(case) for _ in range(16)]
    _, binding, _, connector, _ = case
    assert len(connector.calls) == 30
    assert results[-1][0].error is not None
    assert results[-1][0].error.code == "CONTENT_UNAVAILABLE"
    assert not results[-1][0].error.retryable
    http_audits = [
        record
        for record in binding.port.audit_records
        if record.invocation_id.startswith("research-http-")
    ]
    assert sum(record.actual.calls for record in http_audits) == 30
    assert sum(record.actual.bytes for record in http_audits) == 15 * 7
    assert (await binding.port.snapshot(binding.scope)).used.calls == 46
    other_source, _ = await invoke(
        case,
        args={
            "request_id": "hn-request",
            "source_id": "hacker_news_api",
            "candidate_id": "hn-1",
            "url": "https://hacker-news.firebaseio.com/v0/item/123.json",
        },
    )
    assert other_source.error.code == "CONTENT_UNAVAILABLE"
    assert len(connector.calls) == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_body_permit_is_released_when_parent_reservation_does_not_dispatch(
    monkeypatch, cancel
):
    from efficiency_platform_agent.core.budget_lease import BudgetExhaustedError
    from efficiency_platform_agent.providers.research.transport import (
        HttpBudgetContext,
        ResearchFetchError,
    )
    from tests.contract.providers.research_v2.test_transport import (
        PUBLIC,
        _Connector,
        _lease,
        _request,
        _Resolver,
        _response,
        _transport,
    )

    _, binding, *_ = setup()
    quota = module().LocalResearchBodyHttpQuota(binding)
    original = binding.port.reserve

    async def reject(*args, **kwargs):
        raise asyncio.CancelledError if cancel else BudgetExhaustedError()

    monkeypatch.setattr(binding.port, "reserve", reject)
    connector = _Connector([_response()])
    lease = replace(
        _lease(_Resolver({"news.example.test": (PUBLIC,)})),
        budget_context=HttpBudgetContext(
            binding.port, binding.scope, "body-quota", binding.version
        ),
        dispatch_quota=quota,
    )
    with bind_budget_execution(binding):
        for _ in range(31):
            with pytest.raises(
                asyncio.CancelledError if cancel else ResearchFetchError
            ):
                await _transport(connector).fetch(_request(), lease)
        assert quota.dispatched == 0
        assert connector.targets == []
        assert binding.port.audit_records == ()
        monkeypatch.setattr(binding.port, "reserve", original)
        await _transport(connector).fetch(_request(), lease)
    assert len(connector.targets) == quota.dispatched == 1


@pytest.mark.asyncio
async def test_discovery_does_not_consume_exhausted_body_http_quota():
    _, binding, context, connector, resolver = setup(
        connector=Connector(
            [
                PinnedResponse(
                    200,
                    {"content-type": "application/rss+xml"},
                    (b"<rss><channel></channel></rss>",),
                ),
            ]
        )
    )
    quota = module().LocalResearchBodyHttpQuota(binding)
    runtime = module().build_local_research_tools(
        descriptors=(source(body=True),),
        binding=binding,
        run_context=context,
        network_limits=module().LocalResearchNetworkLimits(),
        body_http_quota=quota,
        connector=connector,
        resolver=resolver,
        now=lambda: NOW,
    )
    with bind_budget_execution(binding):
        for _ in range(30):
            quota.reserve().dispatch()
    result, _ = await invoke(
        (runtime, binding, context, connector, resolver), discover=True
    )
    assert result.error is None
    assert len(connector.calls) == 1
    assert quota.dispatched == 30


class Signal:
    def __init__(self):
        self.event = asyncio.Event()

    def is_requested(self):
        return self.event.is_set()

    async def wait_requested(self):
        await self.event.wait()


def setup(
    *,
    descriptors=None,
    connector=None,
    resolver=None,
    signal=None,
    network_limits=None,
    run_id="run-1",
):
    context = RunContext(run_id, "tenant-1", "user-1", "trace-1")
    binding = build_local_research_binding(
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        lease_id="lease-1",
        remaining=REMAINING,
        now=NOW,
        clock_ms=lambda: int(NOW.timestamp() * 1000),
    )
    connector, resolver = connector or Connector(), resolver or Resolver()
    descriptors = descriptors or (source(body=True),)
    runtime = module().build_local_research_tools(
        network_limits=network_limits or module().LocalResearchNetworkLimits(),
        descriptors=descriptors,
        binding=binding,
        run_context=context,
        connector=connector,
        resolver=resolver,
        cancellation_signal=signal,
        now=lambda: NOW,
    )
    return runtime, binding, context, connector, resolver


async def invoke(
    case, *, args=None, context=None, bound=True, lease=None, discover=False
):
    runtime, binding, original, _, _ = case
    arguments = args or {
        "request_id": "request-1",
        "source_id": "google_blog_rss",
        "candidate_id": "candidate-1",
        "url": "https://blog.google/article",
    }
    if discover:
        arguments = {
            "request_id": "request-1",
            "source_id": "google_blog_rss",
            "brief_digest": "a" * 64,
            "query": "private-query",
            "time_window": {
                "start": (NOW - timedelta(days=1)).isoformat(),
                "end": NOW.isoformat(),
                "timezone": "UTC",
                "precision": "day",
                "original_text": "yesterday",
                "anchor": NOW.isoformat(),
            },
            "limit": 5,
        }
        arguments["cursor"] = None
    else:
        arguments = {"etag": None, "last_modified": None, **arguments}
    frozen = _freeze(arguments)
    assert isinstance(frozen, JsonObject)
    request = ToolRequest(
        "2",
        "research.discover.v2" if discover else "research.fetch.v2",
        frozen,
        10_000,
        None,
        "invocation-1",
        False,
        2 * 1024 * 1024,
    )

    async def execute():
        return await runtime.invoke(
            request,
            context or original,
            allowed_tools=frozenset({request.tool_name}),
            granted_permissions=frozenset({"research:read"}),
            remaining_budget=REMAINING,
            lease_context=lease,
        )

    if bound:
        with bind_budget_execution(binding):
            return await execute()
    return await execute()


@pytest.mark.asyncio
async def test_pinned_fetch_uses_original_host_and_parent_http_budget():
    case = setup()
    result, records = await invoke(case)
    assert result.error is None
    assert case[3].calls[0].connect_ip == "8.8.8.8"
    assert case[3].calls[0].tls_server_name == "blog.google"
    assert (await case[1].port.snapshot(case[1].scope)).used.calls == 2
    assert "Original verified" not in str(records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "source",
        "run",
        "tenant",
        "user",
        "missing_binding",
        "lease_schema",
        "host",
        "same_host_unapproved_path",
    ],
)
async def test_forgery_never_reaches_network(kind):
    case = setup(descriptors=(source(body=kind != "same_host_unapproved_path"),))
    args = {
        "request_id": "request-1",
        "source_id": "google_blog_rss",
        "candidate_id": "candidate-1",
        "url": "https://blog.google/article",
    }
    context = case[2]
    if kind == "source":
        args["source_id"] = "invented"
    elif kind in {"run", "tenant", "user"}:
        context = replace(context, **{f"{kind}_id": "forged"})
    elif kind == "lease_schema":
        args["lease_id"] = "forged"
    elif kind == "host":
        args["url"] = "https://unregistered.example/article"
    result, _ = await invoke(
        case, args=args, context=context, bound=kind != "missing_binding"
    )
    assert result.error is not None
    assert case[3].calls == []
    assert case[4].calls == []


@pytest.mark.asyncio
async def test_foreign_lease_rejected_before_network():
    case = setup()
    foreign = setup()[1]
    lease = ToolLeaseContext(foreign.port, foreign.scope, "foreign", 0)
    with pytest.raises(ValueError, match="BOUND_BUDGET_LEASE_MISMATCH"):
        await invoke(case, lease=lease)
    assert case[3].calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rebinding", [False, True])
async def test_redirect_private_address_or_dns_rebinding_blocks_next_connection(
    rebinding,
):
    url = "https://blog.google/second" if rebinding else "https://127.0.0.1/private"
    connector = Connector([PinnedResponse(302, {"location": url}, ())])
    case = setup(connector=connector, resolver=Resolver([("8.8.8.8",), ("127.0.0.1",)]))
    result, _ = await invoke(case)
    assert result.error is not None
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code", [(429, "SOURCE_RATE_LIMITED"), (403, "SOURCE_FORBIDDEN")]
)
async def test_status_failures_are_stable_and_not_retried_by_tool(status, code):
    case = setup(connector=Connector([PinnedResponse(status, {}, ())]))
    result, _ = await invoke(case)
    assert result.error.code == code
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("compressed", [False, True])
async def test_oversize_body_rejected_without_truncated_full_result(compressed):
    raw = b"x" * (2 * 1024 * 1024)
    headers = {"content-type": "text/plain"}
    if compressed:
        raw = gzip.compress(raw)
        headers["content-encoding"] = "gzip"
    case = setup(connector=Connector([PinnedResponse(200, headers, (raw,))]))
    result, _ = await invoke(case)
    assert result.error.code == "CONTENT_REJECTED"
    assert result.output is None


@pytest.mark.asyncio
async def test_cancelled_runtime_and_terminal_budget_make_no_new_requests():
    signal = Signal()
    case = setup(signal=signal)
    signal.event.set()
    result, _ = await invoke(case)
    assert result.error is not None
    assert case[3].calls == []
    case = setup()
    await case[1].port.mark_scope_terminal(case[1].scope, "cancelled")
    result, _ = await invoke(case)
    assert result.error is not None
    assert case[3].calls == []


@pytest.mark.asyncio
async def test_truncated_feed_is_failed_attempt_not_empty_success():
    case = setup(
        connector=Connector(
            [
                PinnedResponse(
                    200,
                    {"content-type": "application/rss+xml"},
                    (b"<rss><channel><item>",),
                )
            ]
        )
    )
    result, records = await invoke(case, discover=True)
    assert result.error is None
    output = _thaw(result.output)
    assert output["attempts"][0]["status"] == "failed"
    assert output["attempts"][0]["error_code"] == "SOURCE_SCHEMA_INVALID"
    assert "private-query" not in str(records)


@pytest.mark.asyncio
async def test_rate_limit_applies_to_each_redirect_hop():
    descriptor = source(body=True)
    descriptor = descriptor.model_copy(
        update={
            "rate_policy": descriptor.rate_policy.model_copy(
                update={"requests": 1, "period_seconds": 1}
            )
        }
    )
    case = setup(
        descriptors=(descriptor,),
        connector=Connector(
            [
                PinnedResponse(302, {"location": "/second"}, ()),
                PinnedResponse(200, {"content-type": "text/plain"}, (b"body",)),
            ]
        ),
    )
    started = time.monotonic()
    result, _ = await invoke(case)
    assert result.error is None
    assert time.monotonic() - started >= 0.9
    assert (await case[1].port.snapshot(case[1].scope)).used.calls == 3


@pytest.mark.asyncio
async def test_metadata_only_discovery_removes_unapproved_platform_body():
    descriptor = source("hacker_news_api")
    descriptor = descriptor.model_copy(
        update={
            "content_policy": descriptor.content_policy.model_copy(
                update={"storage_mode": "metadata_only"}
            )
        }
    )
    case = setup(
        descriptors=(descriptor,),
        connector=Connector(
            [
                PinnedResponse(200, {"content-type": "application/json"}, (b"[123]",)),
                PinnedResponse(
                    200,
                    {"content-type": "application/json"},
                    (
                        b'{"id":123,"title":"Ask HN","type":"story","time":1789650000,"text":"unapproved user body"}',
                    ),
                ),
            ]
        ),
    )
    from efficiency_platform_agent.capabilities.research.v2.acquisition import (
        AcquisitionExecutor,
        AcquisitionRuntimeContextV2,
        DiscoveryActionV2,
    )
    from efficiency_platform_agent.capabilities.research.v2.attempts import (
        InMemorySourceAttemptLedger,
    )
    from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
    from efficiency_platform_agent.tools.external.research import (
        ResearchDiscoverArgumentsV2,
    )

    action = DiscoveryActionV2(
        "action-hn",
        ResearchDiscoverArgumentsV2(
            request_id="request-hn",
            source_id="hacker_news_api",
            brief_digest="a" * 64,
            query="Ask",
            time_window=ResolvedTimeWindow(
                start=NOW - timedelta(days=2),
                end=NOW + timedelta(days=1),
                timezone="UTC",
                precision="day",
                original_text="last days",
                anchor=NOW,
            ),
            limit=1,
        ),
    )
    ctx = AcquisitionRuntimeContextV2(
        case[2],
        frozenset({"hacker_news_api"}),
        frozenset({"research:read"}),
        REMAINING,
        time.monotonic() + 60,
    )
    with bind_budget_execution(case[1]):
        result = await AcquisitionExecutor(
            case[0], InMemorySourceAttemptLedger()
        ).execute_discovery(action, ctx)
    assert result.batch is not None
    assert len(result.batch.candidates) == 1
    assert result.batch.candidates[0].content_scope == "none"
    assert result.batch.candidates[0].inline_content is None


@pytest.mark.asyncio
async def test_cancel_during_redirect_rate_wait_never_opens_next_socket():
    signal = Signal()
    descriptor = source(body=True)
    descriptor = descriptor.model_copy(
        update={
            "rate_policy": descriptor.rate_policy.model_copy(
                update={"requests": 1, "period_seconds": 3}
            )
        }
    )
    case = setup(
        descriptors=(descriptor,),
        signal=signal,
        connector=Connector([PinnedResponse(302, {"location": "/second"}, ())]),
    )
    task = asyncio.create_task(invoke(case))
    for _ in range(100):
        if case[3].calls:
            break
        await asyncio.sleep(0.001)
    signal.event.set()
    result, _ = await task
    assert result.error is not None
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
async def test_two_concurrent_runs_share_source_rate_but_keep_separate_budgets():
    assert hasattr(module(), "LocalResearchNetworkLimits"), (
        "SHARED_SOURCE_RATE_LIMIT_MISSING"
    )
    shared = module().LocalResearchNetworkLimits()
    descriptor = source(body=True)
    descriptor = descriptor.model_copy(
        update={
            "rate_policy": descriptor.rate_policy.model_copy(
                update={"requests": 1, "period_seconds": 1}
            )
        }
    )
    first = setup(descriptors=(descriptor,), network_limits=shared, run_id="run-a")
    second = setup(descriptors=(descriptor,), network_limits=shared, run_id="run-b")
    started = time.monotonic()
    results = await asyncio.gather(invoke(first), invoke(second))
    assert all(result.error is None for result, _ in results)
    assert time.monotonic() - started >= 0.9
    assert len(first[3].calls) == len(second[3].calls) == 1
    assert (await first[1].port.snapshot(first[1].scope)).used.calls == 2
    assert (await second[1].port.snapshot(second[1].scope)).used.calls == 2


@pytest.mark.asyncio
async def test_cancelled_run_waiting_shared_source_does_not_cancel_another_run():
    assert hasattr(module(), "LocalResearchNetworkLimits"), (
        "SHARED_SOURCE_RATE_LIMIT_MISSING"
    )
    shared = module().LocalResearchNetworkLimits()
    descriptor = source(body=True)
    descriptor = descriptor.model_copy(
        update={
            "rate_policy": descriptor.rate_policy.model_copy(
                update={"requests": 1, "period_seconds": 1}
            )
        }
    )
    signal = Signal()
    first = setup(descriptors=(descriptor,), network_limits=shared, run_id="first")
    cancelled = setup(
        descriptors=(descriptor,),
        network_limits=shared,
        run_id="cancelled",
        signal=signal,
    )
    survivor = setup(
        descriptors=(descriptor,), network_limits=shared, run_id="survivor"
    )
    assert (await invoke(first))[0].error is None
    waiting = asyncio.create_task(invoke(cancelled))
    await asyncio.sleep(0.01)
    signal.event.set()
    assert (await waiting)[0].error is not None
    assert cancelled[3].calls == []
    assert (await invoke(survivor))[0].error is None
    assert len(survivor[3].calls) == 1


@pytest.mark.asyncio
async def test_terminal_budget_during_rate_wait_prevents_socket_dispatch():
    shared = module().LocalResearchNetworkLimits()
    descriptor = source(body=True)
    descriptor = descriptor.model_copy(
        update={
            "rate_policy": descriptor.rate_policy.model_copy(
                update={"requests": 1, "period_seconds": 1}
            )
        }
    )
    first = setup(descriptors=(descriptor,), network_limits=shared, run_id="first")
    cancelled = setup(
        descriptors=(descriptor,), network_limits=shared, run_id="cancelled"
    )
    assert (await invoke(first))[0].error is None
    waiting = asyncio.create_task(invoke(cancelled))
    await asyncio.sleep(0.02)
    await cancelled[1].port.mark_scope_terminal(cancelled[1].scope, "cancelled")
    result, _ = await waiting
    assert result.error is not None
    assert cancelled[3].calls == []


@pytest.mark.parametrize("omit", [True, False])
def test_local_tool_builder_rejects_missing_shared_limiter(omit):
    case = setup()
    kwargs = {} if omit else {"network_limits": None}
    with pytest.raises(
        (TypeError, ValueError), match="network_limits|LOCAL_NETWORK_LIMITS_REQUIRED"
    ):
        module().build_local_research_tools(
            descriptors=(source(body=True),),
            binding=case[1],
            run_context=case[2],
            connector=case[3],
            resolver=case[4],
            now=lambda: NOW,
            **kwargs,
        )
    assert case[3].calls == []


def test_source_descriptor_has_explicit_empty_by_default_content_endpoints():
    from efficiency_platform_agent.contracts.research_sources_v2 import (
        SourceDescriptorV2,
    )

    assert "content_endpoints" in SourceDescriptorV2.model_fields, (
        "STATIC_CONTENT_ENDPOINTS_MISSING"
    )
    descriptors = load_local_source_descriptors(
        ROOT / "config/research_local_live_sources.toml"
    )
    assert all(item.content_endpoints == () for item in descriptors)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://blog.google/unregistered?lang=en",
        "https://blog.google/article?lang=zh",
        "https://blog.google/article?lang=en&redirect=https%3A%2F%2Fevil.example",
        "https://blog.google/article",
    ],
)
async def test_content_tool_rejects_undeclared_same_host_path_and_query(url):
    descriptor = source(body=True).model_copy(
        update={"content_endpoints": ("https://blog.google/article?lang=en",)}
    )
    case = setup(descriptors=(descriptor,))
    result, _ = await invoke(
        case,
        args={
            "request_id": "request-1",
            "source_id": "google_blog_rss",
            "candidate_id": "candidate-1",
            "url": url,
        },
    )
    assert result.error is not None
    assert result.error.code == "SOURCE_NOT_RUNTIME_ALLOWED"
    assert case[3].calls == []
    assert case[4].calls == []


@pytest.mark.asyncio
async def test_exact_declared_content_endpoint_and_query_can_be_fetched():
    descriptor = source(body=True).model_copy(
        update={"content_endpoints": ("https://blog.google/article?lang=en",)}
    )
    case = setup(descriptors=(descriptor,))
    result, _ = await invoke(
        case,
        args={
            "request_id": "request-1",
            "source_id": "google_blog_rss",
            "candidate_id": "candidate-1",
            "url": "https://blog.google/article?lang=en",
        },
    )
    assert result.error is None
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
async def test_redirect_to_undeclared_same_host_endpoint_never_opens_next_socket():
    descriptor = source(body=True).model_copy(
        update={"content_endpoints": ("https://blog.google/article",)}
    )
    case = setup(
        descriptors=(descriptor,),
        connector=Connector(
            [PinnedResponse(302, {"location": "/private?download=all"}, ())]
        ),
    )
    result, _ = await invoke(case)
    assert result.error is not None
    assert result.error.code == "SOURCE_NOT_RUNTIME_ALLOWED"
    assert result.error.retryable is False
    assert len(case[3].calls) == 1
    assert (await case[1].port.snapshot(case[1].scope)).used.calls == 2


@pytest.mark.asyncio
async def test_genuine_connector_failure_remains_retryable_temporary_failure():
    class FailingConnector(Connector):
        async def request(self, target, **kwargs):
            self.calls.append(target)
            raise OSError("connection interrupted")

    case = setup(connector=FailingConnector())
    result, _ = await invoke(case)
    assert result.error.code == "SOURCE_TEMPORARY_FAILURE"
    assert result.error.retryable is True
    assert len(case[3].calls) == 1
