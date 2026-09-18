"""研究 Tool 的可信范围注入与错误保真测试。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryBatchV2,
    FetchedContentV2,
    SourceAttemptV2,
    SourceUsageV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.run import (
    JsonObject,
    RunContext,
    ToolRequest,
)
from efficiency_platform_agent.providers.research.transport import ResearchFetchError
from efficiency_platform_agent.tools.external.research import (
    ExplicitDocumentFetcherRegistry,
    ExplicitSourceProviderRegistry,
    ResearchDiscoverArgumentsV2,
    ResearchFetchArgumentsV2,
    StaticResearchToolScopeResolver,
    TrustedResearchToolScope,
    research_tool_entries,
)
from efficiency_platform_agent.tools.runtime.registry import ToolRegistry
from efficiency_platform_agent.tools.runtime.service import ToolRuntime


class _Provider:
    def __init__(self, batch: DiscoveryBatchV2) -> None:
        self.batch = batch
        self.requests = []

    async def discover(self, request):
        self.requests.append(request)
        return self.batch.model_copy(update={"request_id": request.request_id})


class _Fetcher:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.requests = []

    async def fetch(self, request):
        self.requests.append(request)
        raise self.error


class _MalformedProvider:
    def __init__(self) -> None:
        self.requests = []

    async def discover(self, request):
        self.requests.append(request)
        return {"unexpected": "shape"}


class _CrossSourceProvider:
    async def discover(self, request):
        batch = _batch()
        return batch.model_copy(
            update={
                "request_id": request.request_id,
                "attempts": (
                    batch.attempts[0].model_copy(update={"source_id": "evil"}),
                ),
            }
        )


class _ReturningFetcher:
    def __init__(self, content: FetchedContentV2) -> None:
        self.content = content
        self.requests = []

    async def fetch(self, request):
        self.requests.append(request)
        return self.content


def _attempt(error_code: str | None = None) -> SourceAttemptV2:
    return SourceAttemptV2(
        attempt_id="attempt-1",
        action_id="request-1",
        source_id="source-1",
        status="failed" if error_code else "success_empty",
        started_at=datetime(2026, 9, 16, tzinfo=UTC),
        finished_at=datetime(2026, 9, 16, 0, 0, 1, tzinfo=UTC),
        returned_count=0,
        filtered_count=0,
        error_code=error_code,
        coverage="unknown",
        lease_id="lease-1",
        usage=SourceUsageV2(requests=1, returned_items=0, downloaded_bytes=0),
    )


def _batch(error_code: str | None = None) -> DiscoveryBatchV2:
    return DiscoveryBatchV2(
        request_id="request-1",
        candidates=(),
        next_cursor=None,
        completeness="unknown" if error_code else "complete",
        coverage="unknown",
        attempts=(_attempt(error_code),),
    )


def _window() -> ResolvedTimeWindow:
    return ResolvedTimeWindow(
        start=datetime(2026, 9, 15, tzinfo=UTC),
        end=datetime(2026, 9, 16, tzinfo=UTC),
        timezone="UTC",
        precision="day",
        original_text="yesterday",
        anchor=datetime(2026, 9, 16, tzinfo=UTC),
    )


def _runtime(provider: _Provider, fetcher: _Fetcher):
    scopes = StaticResearchToolScopeResolver(
        {
            ("tenant-1", "run-1", "source-1"): TrustedResearchToolScope(
                "lease-1", "d" * 64
            )
        }
    )
    entries = research_tool_entries(
        ExplicitSourceProviderRegistry({"source-1": provider}),
        ExplicitDocumentFetcherRegistry({"source-1": fetcher}),
        scopes,
    )
    registry = ToolRegistry()
    for spec, tool in entries:
        registry.register(spec, tool)
    return ToolRuntime(registry), registry


def _context(run_id: str = "run-1") -> RunContext:
    return RunContext("run-1" if run_id == "run-1" else run_id, "tenant-1", "user-1", "trace-1")


def _remaining() -> RemainingBudget:
    return RemainingBudget(10, 10, 10, 10, 10, 10_000)


def _freeze(value: object):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return JsonObject(tuple((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError


def _thaw(value: object):
    if isinstance(value, JsonObject):
        return {key: _thaw(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _discover_request(*, extra: tuple[tuple[str, object], ...] = ()) -> ToolRequest:
    arguments = ResearchDiscoverArgumentsV2(
        request_id="request-1",
        source_id="source-1",
        brief_digest="a" * 64,
        query="AI",
        time_window=_window(),
        cursor=None,
        limit=10,
    ).model_dump(mode="json")
    arguments.update(dict(extra))
    return ToolRequest(
        "2",
        "research.discover.v2",
        _freeze(arguments),
        10_000,
        None,
        "idempotency-1",
        False,
        2 * 1024 * 1024,
    )


@pytest.mark.asyncio
async def test_trusted_scope_is_injected_and_not_public_arguments() -> None:
    provider = _Provider(_batch())
    runtime, _ = _runtime(
        provider,
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_RATE_LIMITED")),
    )

    result, _ = await runtime.invoke(
        _discover_request(),
        _context(),
        allowed_tools=frozenset({"research.discover.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error is None
    assert provider.requests[0].tenant_id == "tenant-1"
    assert provider.requests[0].run_id == "run-1"
    assert provider.requests[0].lease_id == "lease-1"


@pytest.mark.asyncio
async def test_caller_cannot_spoof_tenant_or_lease() -> None:
    provider = _Provider(_batch())
    runtime, _ = _runtime(
        provider,
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_RATE_LIMITED")),
    )

    result, _ = await runtime.invoke(
        _discover_request(extra=(("tenant_id", "evil"),)),
        _context(),
        allowed_tools=frozenset({"research.discover.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "TOOL_ARGUMENT_INVALID"
    assert provider.requests == []


@pytest.mark.asyncio
async def test_rate_limit_reason_survives_tool_governance() -> None:
    provider = _Provider(_batch("SOURCE_RATE_LIMITED"))
    runtime, _ = _runtime(
        provider,
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_RATE_LIMITED")),
    )

    result, records = await runtime.invoke(
        _discover_request(),
        _context(),
        allowed_tools=frozenset({"research.discover.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )
    batch = DiscoveryBatchV2.model_validate(_thaw(result.output))

    assert batch.attempts[0].error_code == "SOURCE_RATE_LIMITED"
    assert len(provider.requests) == 1
    assert len(records) == 1


@pytest.mark.asyncio
async def test_fetch_source_error_is_allowlisted_but_not_retried_by_runtime() -> None:
    provider = _Provider(_batch())
    fetcher = _Fetcher(
        ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_RATE_LIMITED")
    )
    runtime, _ = _runtime(provider, fetcher)
    arguments = ResearchFetchArgumentsV2(
        request_id="fetch-1",
        source_id="source-1",
        candidate_id="candidate-1",
        url="https://news.example.test/a",
        etag=None,
        last_modified=None,
    ).model_dump(mode="json")
    request = ToolRequest(
        "2",
        "research.fetch.v2",
        _freeze(arguments),
        10_000,
        None,
        "fetch-idempotency",
        False,
        2 * 1024 * 1024,
    )

    result, records = await runtime.invoke(
        request,
        _context(),
        allowed_tools=frozenset({"research.fetch.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_RATE_LIMITED"
    assert len(fetcher.requests) == 1
    assert len(records) == 1


def test_only_two_read_only_research_tools_are_registered() -> None:
    _, registry = _runtime(
        _Provider(_batch()),
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_RATE_LIMITED")),
    )
    assert registry.available_tools() == frozenset(
        {"research.discover.v2", "research.fetch.v2"}
    )


@pytest.mark.asyncio
async def test_malformed_provider_result_is_schema_failure_not_retryable() -> None:
    provider = _MalformedProvider()
    runtime, _ = _runtime(  # type: ignore[arg-type]
        provider,
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "FETCH_TIMEOUT")),
    )

    result, records = await runtime.invoke(
        _discover_request(),
        _context(),
        allowed_tools=frozenset({"research.discover.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_SCHEMA_INVALID"
    assert len(provider.requests) == 1
    assert len(records) == 1


@pytest.mark.asyncio
async def test_fetch_timeout_maps_to_transient_source_failure_without_runtime_retry() -> None:
    provider = _Provider(_batch())
    fetcher = _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "FETCH_TIMEOUT"))
    runtime, _ = _runtime(provider, fetcher)
    arguments = ResearchFetchArgumentsV2(
        request_id="fetch-1",
        source_id="source-1",
        candidate_id="candidate-1",
        url="https://news.example.test/a",
        etag=None,
        last_modified=None,
    ).model_dump(mode="json")
    request = ToolRequest(
        "2",
        "research.fetch.v2",
        _freeze(arguments),
        10_000,
        None,
        "fetch-timeout",
        False,
        2 * 1024 * 1024,
    )

    result, records = await runtime.invoke(
        request,
        _context(),
        allowed_tools=frozenset({"research.fetch.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_TEMPORARY_FAILURE"
    assert len(fetcher.requests) == 1
    assert len(records) == 1


@pytest.mark.asyncio
async def test_fetch_auth_required_reason_is_preserved_and_not_retried() -> None:
    provider = _Provider(_batch())
    fetcher = _Fetcher(
        ResearchFetchError("CONTENT_UNAVAILABLE", "SOURCE_AUTH_REQUIRED")
    )
    runtime, _ = _runtime(provider, fetcher)
    arguments = ResearchFetchArgumentsV2(
        request_id="fetch-1",
        source_id="source-1",
        candidate_id="candidate-1",
        url="https://news.example.test/a",
        etag=None,
        last_modified=None,
    ).model_dump(mode="json")
    request = ToolRequest(
        "2",
        "research.fetch.v2",
        _freeze(arguments),
        10_000,
        None,
        "fetch-auth",
        False,
        2 * 1024 * 1024,
    )

    result, records = await runtime.invoke(
        request,
        _context(),
        allowed_tools=frozenset({"research.fetch.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_AUTH_REQUIRED"
    assert len(fetcher.requests) == 1
    assert len(records) == 1


@pytest.mark.asyncio
async def test_discovery_rejects_cross_source_provider_output() -> None:
    provider = _CrossSourceProvider()
    runtime, _ = _runtime(  # type: ignore[arg-type]
        provider,
        _Fetcher(ResearchFetchError("CONTENT_UNAVAILABLE", "FETCH_TIMEOUT")),
    )

    result, records = await runtime.invoke(
        _discover_request(),
        _context(),
        allowed_tools=frozenset({"research.discover.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_SCHEMA_INVALID"
    assert len(records) == 1


@pytest.mark.asyncio
async def test_fetch_rejects_mismatched_request_and_candidate_ids() -> None:
    provider = _Provider(_batch())
    fetcher = _ReturningFetcher(
        FetchedContentV2(
            request_id="different-request",
            candidate_id="different-candidate",
            final_url="https://news.example.test/a",
            media_type="text/plain",
            body=b"body",
            downloaded_bytes=4,
            fetched_at=datetime(2026, 9, 16, tzinfo=UTC),
            status_code=200,
        )
    )
    runtime, _ = _runtime(provider, fetcher)  # type: ignore[arg-type]
    arguments = ResearchFetchArgumentsV2(
        request_id="fetch-1",
        source_id="source-1",
        candidate_id="candidate-1",
        url="https://news.example.test/a",
        etag=None,
        last_modified=None,
    ).model_dump(mode="json")
    request = ToolRequest(
        "2",
        "research.fetch.v2",
        _freeze(arguments),
        10_000,
        None,
        "fetch-mismatch",
        False,
        2 * 1024 * 1024,
    )

    result, records = await runtime.invoke(
        request,
        _context(),
        allowed_tools=frozenset({"research.fetch.v2"}),
        granted_permissions=frozenset({"research:read"}),
        remaining_budget=_remaining(),
    )

    assert result.error and result.error.code == "SOURCE_SCHEMA_INVALID"
    assert len(records) == 1
