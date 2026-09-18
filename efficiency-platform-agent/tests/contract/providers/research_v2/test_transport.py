"""安全研究传输端口的离线契约测试。"""

from __future__ import annotations

import asyncio
import gzip
from dataclasses import dataclass, field
from datetime import UTC

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import FetchRequestV2
from efficiency_platform_agent.core.budget import RemainingBudget
from efficiency_platform_agent.core.budget_lease import (
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.providers.research.transport import (
    FetchLease,
    HttpBudgetContext,
    PinnedResponse,
    ResearchFetchError,
    SafeHttpTransport,
)
from efficiency_platform_agent.security.url_policy import (
    ResearchUrlSourcePolicy,
    UrlPolicy,
)

PUBLIC = "93.184.216.34"


@dataclass
class _Resolver:
    answers: dict[str, tuple[str, ...]]
    calls: list[str] = field(default_factory=list)

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append(f"{host}:{port}")
        return self.answers[host]


class _Connector:
    supports_ip_pinning = True
    supports_tls_server_name = True
    verifies_certificates = True
    uses_environment_proxy = False

    def __init__(self, responses: list[PinnedResponse], *, delay: float = 0.0):
        self.responses = responses
        self.delay = delay
        self.targets = []

    async def request(
        self,
        target,
        *,
        headers,
        connect_timeout,
        request_timeout,
        max_wire_bytes,
    ):
        del headers, connect_timeout, request_timeout, max_wire_bytes
        self.targets.append(target)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.responses.pop(0)


class _UnsafeConnector(_Connector):
    supports_ip_pinning = False


def _request(url: str = "https://news.example.test/a") -> FetchRequestV2:
    return FetchRequestV2(
        request_id="req-1",
        source_id="source-1",
        tenant_id="tenant-1",
        run_id="run-1",
        lease_id="lease-1",
        authorization_scope_digest="d" * 64,
        candidate_id="candidate-1",
        url=url,
    )


def _lease(
    resolver: _Resolver,
    *,
    max_wire_bytes: int = 2 * 1024 * 1024,
    max_decoded_bytes: int = 2 * 1024 * 1024,
    timeout_ms: int = 10_000,
    budget_context: HttpBudgetContext | None = None,
) -> FetchLease:
    return FetchLease(
        source_policy=ResearchUrlSourcePolicy(
            allowed_hosts=("news.example.test", "redirect.example.test")
        ),
        resolver=resolver,
        remaining_budget=RemainingBudget(1, 4, 0, 0, 0, timeout_ms),
        max_wire_bytes=max_wire_bytes,
        max_decoded_bytes=max_decoded_bytes,
        budget_context=budget_context,
    )


def _response(
    body: bytes = b"hello",
    *,
    status: int = 200,
    content_type: str = "text/plain; charset=utf-8",
    **headers: str,
) -> PinnedResponse:
    return PinnedResponse(
        status_code=status,
        headers={"content-type": content_type, **headers},
        body_chunks=(body,),
    )


def _transport(connector: _Connector) -> SafeHttpTransport:
    return SafeHttpTransport(connector, url_policy=UrlPolicy())


@pytest.mark.asyncio
async def test_public_content_is_fetched_through_pinned_target() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector([_response()])

    fetched = await _transport(connector).fetch(_request(), _lease(resolver))

    assert fetched.body == b"hello"
    assert fetched.final_url == "https://news.example.test/a"
    assert fetched.media_type == "text/plain"
    assert fetched.fetched_at.tzinfo == UTC
    assert connector.targets[0].connect_ip == PUBLIC
    assert connector.targets[0].tls_server_name == "news.example.test"


@pytest.mark.asyncio
async def test_redirect_to_private_host_never_connects_private_target() -> None:
    resolver = _Resolver(
        {
            "news.example.test": (PUBLIC,),
            "redirect.example.test": ("169.254.169.254",),
        }
    )
    connector = _Connector(
        [_response(status=302, location="https://redirect.example.test/metadata")]
    )

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(_request(), _lease(resolver))

    assert [target.host for target in connector.targets] == ["news.example.test"]


@pytest.mark.asyncio
async def test_each_redirect_is_resolved_again_to_block_dns_rebinding() -> None:
    class RebindingResolver:
        def __init__(self) -> None:
            self.count = 0

        async def resolve(self, host: str, port: int) -> tuple[str, ...]:
            del host, port
            self.count += 1
            return (PUBLIC,) if self.count == 1 else ("127.0.0.1",)

    resolver = RebindingResolver()
    connector = _Connector([_response(status=302, location="/second")])
    lease = _lease(resolver)  # type: ignore[arg-type]

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(_request(), lease)
    assert len(connector.targets) == 1
    assert resolver.count == 2


@pytest.mark.asyncio
async def test_connector_without_security_capabilities_fails_before_dns() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _UnsafeConnector([_response()])

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(_request(), _lease(resolver))

    assert resolver.calls == []
    assert connector.targets == []


@pytest.mark.asyncio
async def test_object_missing_connector_capabilities_fails_closed() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await SafeHttpTransport(  # type: ignore[arg-type]
            object(), url_policy=UrlPolicy()
        ).fetch(_request(), _lease(resolver))

    assert resolver.calls == []


@pytest.mark.asyncio
async def test_unauthorized_host_is_rejected_before_dns() -> None:
    resolver = _Resolver({})
    connector = _Connector([_response()])

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(
            _request("https://evil.invalid/a"), _lease(resolver)
        )

    assert resolver.calls == []
    assert connector.targets == []


@pytest.mark.asyncio
async def test_compressed_and_decompressed_limits_are_independent() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    compressed = gzip.compress(b"a" * 5000)
    connector = _Connector(
        [_response(compressed, **{"content-encoding": "gzip"})]
    )

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(
            _request(), _lease(resolver, max_wire_bytes=1000, max_decoded_bytes=100)
        )


@pytest.mark.asyncio
async def test_forbidden_media_type_is_rejected() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector([_response(b"%PDF", content_type="application/pdf")])

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(_request(), _lease(resolver))


@pytest.mark.asyncio
async def test_request_timeout_is_narrower_than_remaining_budget() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector([_response()], delay=0.05)

    with pytest.raises(ResearchFetchError, match="CONTENT_UNAVAILABLE"):
        await _transport(connector).fetch(
            _request(), _lease(resolver, timeout_ms=10)
        )


@pytest.mark.asyncio
async def test_redirect_limit_and_http_budget_are_enforced() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector(
        [
            _response(status=302, location=f"/hop-{index}")
            for index in range(1, 5)
        ]
    )

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(_request(), _lease(resolver))
    assert len(connector.targets) == 4


@pytest.mark.asyncio
async def test_oversized_redirect_body_is_rejected() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector(
        [_response(b"x" * 101, status=302, location="/next")]
    )

    with pytest.raises(ResearchFetchError, match="CONTENT_REJECTED"):
        await _transport(connector).fetch(
            _request(), _lease(resolver, max_wire_bytes=100)
        )
    assert len(connector.targets) == 1


@pytest.mark.asyncio
async def test_malformed_success_response_has_schema_error() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector(
        [PinnedResponse(status_code=200, headers={}, body_chunks=(b"body",))]
    )

    with pytest.raises(ResearchFetchError, match="SOURCE_SCHEMA_INVALID"):
        await _transport(connector).fetch(_request(), _lease(resolver))


@pytest.mark.asyncio
async def test_rate_limit_reason_is_preserved_without_reading_as_success() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector(
        [
            PinnedResponse(
                status_code=429,
                headers={"content-type": "text/plain", "retry-after": "7"},
                body_chunks=(b"limited",),
            )
        ]
    )

    with pytest.raises(ResearchFetchError, match="CONTENT_UNAVAILABLE") as captured:
        await _transport(connector).fetch(_request(), _lease(resolver))

    assert captured.value.reason_code == "SOURCE_RATE_LIMITED"
    assert captured.value.http_status == 429
    assert captured.value.response_headers == (("retry-after", "7"),)
    assert captured.value.downloaded_bytes == len(b"limited")


@pytest.mark.asyncio
async def test_401_is_non_retryable_auth_required_reason() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector([_response(b"auth", status=401)])

    with pytest.raises(ResearchFetchError) as captured:
        await _transport(connector).fetch(_request(), _lease(resolver))

    assert captured.value.reason_code == "SOURCE_AUTH_REQUIRED"
    assert captured.value.http_status == 401


@pytest.mark.asyncio
async def test_redirect_hops_are_reserved_and_settled_as_separate_http_calls() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=2,
            max_bytes=10 * 1024 * 1024,
            max_cost_microunits=0,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "http")
    budget_context = HttpBudgetContext(repository, scope, "fetch-1", 0)
    resolver = _Resolver(
        {
            "news.example.test": (PUBLIC,),
            "redirect.example.test": (PUBLIC,),
        }
    )
    connector = _Connector(
        [
            _response(
                b"hop",
                status=302,
                location="https://redirect.example.test/final",
            ),
            _response(b"ok"),
        ]
    )

    result = await _transport(connector).fetch(
        _request(),
        _lease(resolver, budget_context=budget_context),
    )
    snapshot = await repository.snapshot(scope)

    assert result.body == b"ok"
    assert result.request_count == 2
    assert len(connector.targets) == 2
    assert repository.dispatched_invocation_count == 2
    assert snapshot.used.calls == 2
    assert snapshot.used.bytes == len(b"hop") + len(b"ok")
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_http_budget_exhaustion_blocks_next_redirect_dispatch() -> None:
    repository = InMemoryBudgetLeaseRepository(
        BudgetLimits(
            max_calls=1,
            max_bytes=10 * 1024 * 1024,
            max_cost_microunits=0,
        )
    )
    scope = BudgetScope("tenant-1", "run-1", "research", "http")
    budget_context = HttpBudgetContext(repository, scope, "fetch-1", 0)
    resolver = _Resolver(
        {
            "news.example.test": (PUBLIC,),
            "redirect.example.test": (PUBLIC,),
        }
    )
    connector = _Connector(
        [
            _response(
                b"hop",
                status=302,
                location="https://redirect.example.test/final",
            ),
            _response(b"must-not-run"),
        ]
    )

    with pytest.raises(ResearchFetchError) as captured:
        await _transport(connector).fetch(
            _request(),
            _lease(resolver, budget_context=budget_context),
        )
    snapshot = await repository.snapshot(scope)

    assert captured.value.reason_code == "FETCH_BUDGET_EXHAUSTED"
    assert len(connector.targets) == 1
    assert repository.dispatched_invocation_count == 1
    assert snapshot.used.calls == 1
    assert snapshot.reserved.calls == 0


@pytest.mark.asyncio
async def test_304_without_content_type_is_available_only_to_cache_wrapper() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    connector = _Connector(
        [PinnedResponse(status_code=304, headers={"etag": '"v1"'}, body_chunks=())]
    )

    fetched = await _transport(connector).fetch(_request(), _lease(resolver))

    assert fetched.status_code == 304
    assert fetched.body == b""
    assert fetched.media_type == "application/x-not-modified"


@pytest.mark.asyncio
async def test_truncated_compressed_body_is_schema_error() -> None:
    resolver = _Resolver({"news.example.test": (PUBLIC,)})
    truncated = gzip.compress(b"article")[:-4]
    connector = _Connector(
        [_response(truncated, **{"content-encoding": "gzip"})]
    )

    with pytest.raises(ResearchFetchError, match="SOURCE_SCHEMA_INVALID"):
        await _transport(connector).fetch(_request(), _lease(resolver))
