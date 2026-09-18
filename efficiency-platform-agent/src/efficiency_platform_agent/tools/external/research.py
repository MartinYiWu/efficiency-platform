"""经 Tool Runtime 治理的研究发现与正文获取工具。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from efficiency_platform_agent.contracts.research_ports_v2 import SourceProvider
from efficiency_platform_agent.contracts.research_sources_v2 import (
    DiscoveryBatchV2,
    DiscoveryRequestV2,
    FetchedContentV2,
    FetchRequestV2,
)
from efficiency_platform_agent.contracts.temporal_v2 import ResolvedTimeWindow
from efficiency_platform_agent.core.ports import Tool
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    JsonValue,
    RunContext,
    ToolError,
    ToolRequest,
    ToolResult,
)
from efficiency_platform_agent.providers.research._adapter_support import (
    ResearchDocumentFetcher,
)
from efficiency_platform_agent.providers.research.transport import ResearchFetchError
from efficiency_platform_agent.tools.runtime.contracts import ToolSpec


class _ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResearchDiscoverArgumentsV2(_ToolModel):
    request_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    brief_digest: str = Field(min_length=16, max_length=128)
    query: str = Field(min_length=1, max_length=2_000)
    time_window: ResolvedTimeWindow
    cursor: str | None = Field(default=None, max_length=2_000)
    limit: int = Field(ge=1, le=500)


class ResearchFetchArgumentsV2(_ToolModel):
    request_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=4_096)
    etag: str | None = Field(default=None, max_length=512)
    last_modified: str | None = Field(default=None, max_length=512)


class ResearchFetchedResultV2(_ToolModel):
    request_id: str
    candidate_id: str
    final_url: str
    media_type: str
    body_base64: str
    downloaded_bytes: int = Field(ge=0)
    request_count: int = Field(ge=1, le=64)
    fetched_at: str
    status_code: int = Field(ge=100, le=599)
    etag: str | None = None
    last_modified: str | None = None
    response_headers: tuple[tuple[str, str], ...] = ()
    cache_status: str

    @classmethod
    def from_content(cls, content: FetchedContentV2) -> ResearchFetchedResultV2:
        return cls(
            request_id=content.request_id,
            candidate_id=content.candidate_id,
            final_url=content.final_url,
            media_type=content.media_type,
            body_base64=base64.b64encode(content.body).decode("ascii"),
            downloaded_bytes=content.downloaded_bytes,
            request_count=content.request_count,
            fetched_at=content.fetched_at.isoformat(),
            status_code=content.status_code,
            etag=content.etag,
            last_modified=content.last_modified,
            response_headers=content.response_headers,
            cache_status=content.cache_status,
        )


@dataclass(frozen=True, slots=True)
class TrustedResearchToolScope:
    lease_id: str
    authorization_scope_digest: str

    def __post_init__(self) -> None:
        if not self.lease_id.strip() or len(self.authorization_scope_digest) != 64:
            raise ValueError("RESEARCH_TOOL_SCOPE_INVALID")


class ResearchToolScopeError(RuntimeError):
    code = "SOURCE_NOT_RUNTIME_ALLOWED"

    def __init__(self) -> None:
        super().__init__(self.code)


class ResearchToolScopeResolver(Protocol):
    async def resolve(
        self, context: RunContext, source_id: str
    ) -> TrustedResearchToolScope: ...


class StaticResearchToolScopeResolver:
    def __init__(
        self,
        scopes: dict[tuple[str, str, str], TrustedResearchToolScope],
    ) -> None:
        self._scopes = dict(scopes)

    async def resolve(
        self, context: RunContext, source_id: str
    ) -> TrustedResearchToolScope:
        try:
            return self._scopes[(context.tenant_id, context.run_id, source_id)]
        except KeyError as exc:
            raise ResearchToolScopeError from exc


class ExplicitSourceProviderRegistry:
    def __init__(self, providers: dict[str, SourceProvider]) -> None:
        self._providers = dict(providers)

    def get(self, source_id: str) -> SourceProvider:
        try:
            return self._providers[source_id]
        except KeyError as exc:
            raise ResearchToolScopeError from exc


class ExplicitDocumentFetcherRegistry:
    def __init__(self, fetchers: dict[str, ResearchDocumentFetcher]) -> None:
        self._fetchers = dict(fetchers)

    def get(self, source_id: str) -> ResearchDocumentFetcher:
        try:
            return self._fetchers[source_id]
        except KeyError as exc:
            raise ResearchToolScopeError from exc


class ResearchDiscoverTool:
    descriptor = ExtensionDescriptor(
        name="research.discover.v2",
        semantic_version="2.0.0",
        input_schema_version="2",
        output_schema_version="2",
        permissions=frozenset({"research:read"}),
        budget=ExecutionBudget(1, 1, 0, 0, 10_000, 0),
        termination_conditions=frozenset({"completed", "failed"}),
        checkpoint_version="2",
    )

    def __init__(
        self,
        providers: ExplicitSourceProviderRegistry,
        scope_resolver: ResearchToolScopeResolver,
    ) -> None:
        self.providers = providers
        self.scope_resolver = scope_resolver

    async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
        try:
            arguments = ResearchDiscoverArgumentsV2.model_validate(
                _thaw_object(request.arguments)
            )
            scope = await self.scope_resolver.resolve(context, arguments.source_id)
            provider = self.providers.get(arguments.source_id)
            raw_batch = await provider.discover(
                DiscoveryRequestV2(
                    **arguments.model_dump(mode="python"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    lease_id=scope.lease_id,
                    authorization_scope_digest=scope.authorization_scope_digest,
                )
            )
            try:
                batch = DiscoveryBatchV2.model_validate(raw_batch)
            except (TypeError, ValueError, AttributeError):
                return _error("SOURCE_SCHEMA_INVALID", retryable=False)
            if (
                batch.request_id != arguments.request_id
                or any(
                    item.source_id != arguments.source_id
                    for item in batch.candidates
                )
                or any(
                    item.source_id != arguments.source_id
                    or item.action_id != arguments.request_id
                    or item.lease_id != scope.lease_id
                    for item in batch.attempts
                )
            ):
                return _error("SOURCE_SCHEMA_INVALID", retryable=False)
            return _success(batch, "2")
        except ResearchToolScopeError:
            return _error("SOURCE_NOT_RUNTIME_ALLOWED", retryable=False)
        except Exception:  # noqa: BLE001 - Tool 边界不得泄露 Provider 异常
            return _error("SOURCE_TEMPORARY_FAILURE", retryable=True)


class ResearchFetchTool:
    descriptor = ExtensionDescriptor(
        name="research.fetch.v2",
        semantic_version="2.0.0",
        input_schema_version="2",
        output_schema_version="2",
        permissions=frozenset({"research:read"}),
        budget=ExecutionBudget(1, 1, 0, 0, 10_000, 0),
        termination_conditions=frozenset({"completed", "failed"}),
        checkpoint_version="2",
    )

    def __init__(
        self,
        fetchers: ExplicitDocumentFetcherRegistry,
        scope_resolver: ResearchToolScopeResolver,
    ) -> None:
        self.fetchers = fetchers
        self.scope_resolver = scope_resolver

    async def invoke(self, request: ToolRequest, context: RunContext) -> ToolResult:
        try:
            arguments = ResearchFetchArgumentsV2.model_validate(
                _thaw_object(request.arguments)
            )
            scope = await self.scope_resolver.resolve(context, arguments.source_id)
            fetcher = self.fetchers.get(arguments.source_id)
            raw_content = await fetcher.fetch(
                FetchRequestV2(
                    **arguments.model_dump(mode="python"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    lease_id=scope.lease_id,
                    authorization_scope_digest=scope.authorization_scope_digest,
                )
            )
            try:
                content = FetchedContentV2.model_validate(raw_content)
            except (TypeError, ValueError, AttributeError):
                return _error("SOURCE_SCHEMA_INVALID", retryable=False)
            if (
                content.request_id != arguments.request_id
                or content.candidate_id != arguments.candidate_id
            ):
                return _error("SOURCE_SCHEMA_INVALID", retryable=False)
            return _success(ResearchFetchedResultV2.from_content(content), "2")
        except ResearchToolScopeError:
            return _error("SOURCE_NOT_RUNTIME_ALLOWED", retryable=False)
        except ResearchFetchError as exc:
            code = _fetch_error_code(exc)
            return _error(
                code,
                retryable=code in {"SOURCE_RATE_LIMITED", "SOURCE_TEMPORARY_FAILURE"},
            )
        except Exception:  # noqa: BLE001 - Tool 边界不得泄露 Provider 异常
            return _error("SOURCE_TEMPORARY_FAILURE", retryable=True)


def research_tool_entries(
    providers: ExplicitSourceProviderRegistry,
    fetchers: ExplicitDocumentFetcherRegistry,
    scope_resolver: ResearchToolScopeResolver,
) -> tuple[tuple[ToolSpec, Tool], ...]:
    discover = ResearchDiscoverTool(providers, scope_resolver)
    fetch = ResearchFetchTool(fetchers, scope_resolver)
    return (
        (
            _spec(
                discover,
                ResearchDiscoverArgumentsV2,
                DiscoveryBatchV2,
            ),
            discover,
        ),
        (_spec(fetch, ResearchFetchArgumentsV2, ResearchFetchedResultV2), fetch),
    )


def _spec(tool: Tool, arguments: type[BaseModel], result: type[BaseModel]) -> ToolSpec:
    descriptor = tool.descriptor
    return ToolSpec(
        tool_name=descriptor.name,
        semantic_version=descriptor.semantic_version,
        owner="research-platform",
        argument_schema_version=descriptor.input_schema_version,
        result_schema_version=descriptor.output_schema_version,
        argument_model=arguments,
        result_model=result,
        required_permissions=descriptor.permissions,
        has_side_effects=False,
        max_attempts=1,
        timeout_ms=10_000,
        max_output_bytes=2 * 1024 * 1024,
    )


def _success(model: BaseModel, contract_version: str) -> ToolResult:
    data = model.model_dump(mode="json")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return ToolResult(
        contract_version,
        _freeze(data),
        None,
        len(encoded),
        False,
    )


def _error(code: str, *, retryable: bool) -> ToolResult:
    return ToolResult(
        "2",
        None,
        ToolError(code, "research_source", retryable, "研究来源调用失败", "none"),
        0,
        False,
    )


def _fetch_error_code(exc: ResearchFetchError) -> str:
    if exc.reason_code.startswith("SOURCE_"):
        return exc.reason_code
    if exc.reason_code in {
        "DNS_RESOLUTION_FAILED",
        "FETCH_TIMEOUT",
        "FETCH_TRANSPORT_FAILED",
    }:
        return "SOURCE_TEMPORARY_FAILURE"
    return exc.code


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return JsonObject(tuple((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("RESEARCH_TOOL_JSON_INVALID")


def _thaw(value: JsonValue) -> object:
    if isinstance(value, JsonObject):
        return {key: _thaw(item) for key, item in value.items}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _thaw_object(value: JsonObject) -> dict[str, object]:
    return {key: _thaw(item) for key, item in value.items}


assert isinstance(ResearchDiscoverTool, type)


__all__ = [
    "ExplicitDocumentFetcherRegistry",
    "ExplicitSourceProviderRegistry",
    "ResearchDiscoverArgumentsV2",
    "ResearchDiscoverTool",
    "ResearchFetchArgumentsV2",
    "ResearchFetchTool",
    "ResearchFetchedResultV2",
    "ResearchToolScopeError",
    "ResearchToolScopeResolver",
    "StaticResearchToolScopeResolver",
    "TrustedResearchToolScope",
    "research_tool_entries",
]
