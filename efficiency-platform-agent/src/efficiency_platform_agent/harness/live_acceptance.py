"""服务器端真实验收授权、幂等执行与 BudgetLease 硬绑定。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast, runtime_checkable

from efficiency_platform_agent.contracts.conversation import ConversationMessageV1
from efficiency_platform_agent.contracts.live_acceptance_v2 import (
    LIVE_ACCEPTANCE_CASE_PROMPTS,
    LiveAcceptanceCaseResultV1,
    LiveAcceptanceRequestV1,
    LiveAcceptanceViewV1,
)
from efficiency_platform_agent.core.budget_execution import (
    BudgetExecutionBinding,
    bind_budget_execution,
)
from efficiency_platform_agent.core.budget_lease import (
    BudgetLeaseError,
    BudgetLimits,
    BudgetScope,
    InMemoryBudgetLeaseRepository,
)
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.persistence.research_budget import (
    PostgresBudgetLeaseRepository,
)

if TYPE_CHECKING:
    from efficiency_platform_agent.conversation.service import ConversationService
    from efficiency_platform_agent.harness.service import AgentRuntimeService

_REQUIRED_ACTIONS = frozenset({"model_evaluation", "source_read"})
_SOURCE_REQUIRED_CASES = frozenset(
    {"yesterday_ai", "last_week_topic", "exact_five", "rewrite_wechat"}
)
_MODEL_REQUIRED_CASES = frozenset(
    {"yesterday_ai", "last_week_topic", "exact_five", "rewrite_wechat"}
)


class LiveAcceptanceError(RuntimeError):
    """真实验收在任何外部调用之前返回的稳定拒绝。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class LiveAcceptanceAuthorization:
    """由服务器端可信配置加载的授权事实。"""

    authorization_id: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    allowed_actions: frozenset[str]
    allowed_case_ids: tuple[str, ...]
    allowed_tenant_ids: tuple[str, ...]
    max_budget_microunits: int

    def __post_init__(self) -> None:
        if (
            not self.authorization_id.strip()
            or len(self.authorization_id) > 128
            or not self.approved_by.strip()
            or self.approved_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.approved_at >= self.expires_at
            or not self.allowed_actions
            or any(not item.strip() for item in self.allowed_actions)
            or not self.allowed_case_ids
            or len(set(self.allowed_case_ids)) != len(self.allowed_case_ids)
            or any(
                item not in LIVE_ACCEPTANCE_CASE_PROMPTS
                for item in self.allowed_case_ids
            )
            or not self.allowed_tenant_ids
            or len(set(self.allowed_tenant_ids)) != len(self.allowed_tenant_ids)
            or any(not item.strip() for item in self.allowed_tenant_ids)
            or isinstance(self.max_budget_microunits, bool)
            or self.max_budget_microunits <= 0
        ):
            raise ValueError("LIVE_AUTHORIZATION_INVALID")


@runtime_checkable
class LiveAcceptanceAuthorizationStore(Protocol):
    def get(self, authorization_id: str) -> LiveAcceptanceAuthorization | None: ...


class InMemoryLiveAcceptanceAuthorizationStore:
    """启动时注入的只读授权集合；不接受客户端创建授权。"""

    def __init__(self, records: tuple[LiveAcceptanceAuthorization, ...]) -> None:
        indexed = {record.authorization_id: record for record in records}
        if len(indexed) != len(records):
            raise ValueError("LIVE_AUTHORIZATION_DUPLICATED")
        self._records = indexed

    def get(self, authorization_id: str) -> LiveAcceptanceAuthorization | None:
        return self._records.get(authorization_id)


class JsonLiveAcceptanceAuthorizationStore(
    InMemoryLiveAcceptanceAuthorizationStore
):
    """从服务器本地显式路径加载授权；不接受请求体或环境变量中的授权。"""

    @classmethod
    def from_files(
        cls, paths: tuple[Path, ...]
    ) -> JsonLiveAcceptanceAuthorizationStore:
        if not paths or len(paths) > 32 or len(set(paths)) != len(paths):
            raise ValueError("LIVE_AUTHORIZATION_FILES_INVALID")
        records: list[LiveAcceptanceAuthorization] = []
        required_fields = {
            "version",
            "authorization_id",
            "approved_by",
            "approved_at",
            "expires_at",
            "allowed_actions",
            "allowed_case_ids",
            "allowed_tenant_ids",
            "max_budget_microunits",
        }
        try:
            for path in paths:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or set(payload) != required_fields:
                    raise ValueError("LIVE_AUTHORIZATION_INVALID")
                if payload["version"] != "x04-live-authorization/1":
                    raise ValueError("LIVE_AUTHORIZATION_INVALID")
                if not (
                    isinstance(payload["authorization_id"], str)
                    and isinstance(payload["approved_by"], str)
                    and isinstance(payload["approved_at"], str)
                    and isinstance(payload["expires_at"], str)
                    and isinstance(payload["max_budget_microunits"], int)
                    and not isinstance(payload["max_budget_microunits"], bool)
                ):
                    raise TypeError("LIVE_AUTHORIZATION_INVALID")
                approved_at = datetime.fromisoformat(payload["approved_at"])
                expires_at = datetime.fromisoformat(payload["expires_at"])
                allowed_actions = payload["allowed_actions"]
                allowed_cases = payload["allowed_case_ids"]
                allowed_tenants = payload["allowed_tenant_ids"]
                if not (
                    isinstance(allowed_actions, list)
                    and all(isinstance(item, str) for item in allowed_actions)
                    and isinstance(allowed_cases, list)
                    and all(isinstance(item, str) for item in allowed_cases)
                    and isinstance(allowed_tenants, list)
                    and all(isinstance(item, str) for item in allowed_tenants)
                ):
                    raise ValueError("LIVE_AUTHORIZATION_INVALID")
                records.append(
                    LiveAcceptanceAuthorization(
                        authorization_id=payload["authorization_id"],
                        approved_by=payload["approved_by"],
                        approved_at=approved_at,
                        expires_at=expires_at,
                        allowed_actions=frozenset(allowed_actions),
                        allowed_case_ids=tuple(allowed_cases),
                        allowed_tenant_ids=tuple(allowed_tenants),
                        max_budget_microunits=payload[
                            "max_budget_microunits"
                        ],
                    )
                )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            KeyError,
            ValueError,
        ) as exc:
            raise ValueError("LIVE_AUTHORIZATION_INVALID") from exc
        return cls(tuple(records))


LiveAcceptanceBudgetBinding = BudgetExecutionBinding


@runtime_checkable
class LiveAcceptanceBudgetBinder(Protocol):
    def bind(
        self,
        authorization: LiveAcceptanceAuthorization,
        request: LiveAcceptanceRequestV1,
        *,
        tenant_id: str,
    ) -> LiveAcceptanceBudgetBinding: ...


@runtime_checkable
class LiveAcceptanceCaseRunner(Protocol):
    async def run_case(
        self,
        case_id: str,
        prompt: str,
        binding: LiveAcceptanceBudgetBinding,
    ) -> LiveAcceptanceCaseResultV1 | Mapping[str, object]: ...


class ConversationLiveAcceptanceRunner:
    """在同一会话、同一父租约下执行冻结用例并保守核验结果。"""

    def __init__(self, conversation: object, runtime: object) -> None:
        if not callable(getattr(conversation, "submit", None)):
            raise TypeError("LIVE_CONVERSATION_SERVICE_INVALID")
        if not all(
            callable(getattr(runtime, name, None))
            for name in ("wait_for_background_tasks", "get_run")
        ):
            raise TypeError("LIVE_RUNTIME_SERVICE_INVALID")
        self._conversation = cast("ConversationService", conversation)
        self._runtime = cast("AgentRuntimeService", runtime)

    async def run_case(
        self,
        case_id: str,
        prompt: str,
        binding: LiveAcceptanceBudgetBinding,
    ) -> LiveAcceptanceCaseResultV1:
        request_digest = hashlib.sha256(
            f"{binding.lease_id}\n{case_id}".encode()
        ).hexdigest()[:24]
        message = ConversationMessageV1(
            message=prompt,
            request_id=f"live-case-{request_digest}",
            user_id="x04-live-acceptance",
        )
        with bind_budget_execution(binding):
            submitted = await self._conversation.submit(
                binding.lease_id,
                binding.scope.tenant_id,
                message,
            )
        await self._runtime.wait_for_background_tasks()
        run = await self._runtime.get_run(
            submitted.run_id,
            binding.scope.tenant_id,
        )
        model_verified = bool(
            not run.usage.estimated
            and (run.usage.input_tokens > 0 or run.usage.output_tokens > 0)
        )
        source_verified = _has_citations(run.output)
        status: Literal["PASS", "PARTIAL", "FAILED"]
        if (
            run.status is not RunStatus.SUCCEEDED
            or (case_id in _SOURCE_REQUIRED_CASES and not source_verified)
            or (case_id in _MODEL_REQUIRED_CASES and not model_verified)
        ):
            status = "FAILED"
        elif run.degraded:
            status = "PARTIAL"
        else:
            status = "PASS"
        return LiveAcceptanceCaseResultV1(
            case_id=case_id,
            status=status,
            run_id=run.run_id,
            real_model_verified=model_verified,
            real_source_verified=source_verified,
        )


@dataclass(frozen=True, slots=True)
class _BoundEntry:
    fingerprint: str
    binding: LiveAcceptanceBudgetBinding


class InMemoryLiveAcceptanceBudgetBinder:
    """X04 离线验收 Binder；生产实现必须由 X01 持久化端口替换。"""

    def __init__(self, *, clock_ms: Callable[[], int] | None = None) -> None:
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._entries: dict[tuple[str, str], _BoundEntry] = {}

    @property
    def binding_count(self) -> int:
        return len(self._entries)

    def binding_for(
        self, tenant_id: str, authorization_id: str
    ) -> LiveAcceptanceBudgetBinding:
        return self._entries[(tenant_id, authorization_id)].binding

    def bind(
        self,
        authorization: LiveAcceptanceAuthorization,
        request: LiveAcceptanceRequestV1,
        *,
        tenant_id: str,
    ) -> LiveAcceptanceBudgetBinding:
        fingerprint = _request_fingerprint(request)
        key = (tenant_id, authorization.authorization_id)
        existing = self._entries.get(key)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise LiveAcceptanceError("LIVE_AUTHORIZATION_REUSED")
            return existing.binding
        session_digest = hashlib.sha256(
            f"{tenant_id}\n{request.request_id}\n{fingerprint}".encode()
        ).hexdigest()[:32]
        session_id = f"live-acceptance-{session_digest}"
        scope = BudgetScope(tenant_id, session_id, "live_acceptance", "all")
        repository = InMemoryBudgetLeaseRepository(
            BudgetLimits(
                max_calls=128,
                max_bytes=64 * 1024 * 1024,
                max_cost_microunits=request.requested_budget_microunits,
                max_input_tokens=1_000_000,
                max_output_tokens=1_000_000,
                deadline_epoch_ms=int(authorization.expires_at.timestamp() * 1_000),
            ),
            clock_ms=self._clock_ms,
        )
        authorization_digest = hashlib.sha256(
            (
                f"{authorization.authorization_id}\n{tenant_id}\n"
                f"{request.request_id}\n{fingerprint}"
            ).encode()
        ).hexdigest()
        binding = LiveAcceptanceBudgetBinding(
            repository,
            scope,
            session_id,
            authorization_digest,
        )
        self._entries[key] = _BoundEntry(fingerprint, binding)
        return binding


class PostgresLiveAcceptanceBudgetBinder:
    """用 X01 PostgreSQL 权威账本绑定真实验收预算。"""

    def __init__(self, connection: object, schema: str) -> None:
        if connection is None:
            raise ValueError("LIVE_POSTGRES_CONNECTION_REQUIRED")
        self._connection = connection
        self._schema = schema
        self._entries: dict[tuple[str, str], _BoundEntry] = {}

    @property
    def binding_count(self) -> int:
        return len(self._entries)

    def bind(
        self,
        authorization: LiveAcceptanceAuthorization,
        request: LiveAcceptanceRequestV1,
        *,
        tenant_id: str,
    ) -> LiveAcceptanceBudgetBinding:
        fingerprint = _request_fingerprint(request)
        key = (tenant_id, authorization.authorization_id)
        existing = self._entries.get(key)
        if existing is not None:
            if existing.fingerprint != fingerprint:
                raise LiveAcceptanceError("LIVE_AUTHORIZATION_REUSED")
            return existing.binding
        session_digest = hashlib.sha256(
            f"{tenant_id}\n{request.request_id}\n{fingerprint}".encode()
        ).hexdigest()[:32]
        session_id = f"live-acceptance-{session_digest}"
        scope = BudgetScope(tenant_id, session_id, "live_acceptance", "all")
        port = PostgresBudgetLeaseRepository(
            self._connection,
            self._schema,
            BudgetLimits(
                max_calls=128,
                max_bytes=64 * 1024 * 1024,
                max_cost_microunits=request.requested_budget_microunits,
                max_input_tokens=1_000_000,
                max_output_tokens=1_000_000,
                deadline_epoch_ms=int(authorization.expires_at.timestamp() * 1_000),
            ),
        )
        authorization_digest = hashlib.sha256(
            (
                f"{authorization.authorization_id}\n{tenant_id}\n"
                f"{request.request_id}\n{fingerprint}"
            ).encode()
        ).hexdigest()
        binding = LiveAcceptanceBudgetBinding(
            port,
            scope,
            session_id,
            authorization_digest,
        )
        self._entries[key] = _BoundEntry(fingerprint, binding)
        return binding


@dataclass(frozen=True, slots=True)
class _PendingEntry:
    fingerprint: str
    future: asyncio.Future[LiveAcceptanceViewV1]


class LiveAcceptanceService:
    """服务器端校验授权并在一个硬租约内顺序执行冻结用例。"""

    def __init__(
        self,
        *,
        authorizations: LiveAcceptanceAuthorizationStore,
        budget_binder: LiveAcceptanceBudgetBinder,
        runner: LiveAcceptanceCaseRunner,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(authorizations, LiveAcceptanceAuthorizationStore):
            raise TypeError("LIVE_AUTHORIZATION_STORE_INVALID")
        if not isinstance(budget_binder, LiveAcceptanceBudgetBinder):
            raise TypeError("LIVE_BUDGET_BINDER_INVALID")
        if not isinstance(runner, LiveAcceptanceCaseRunner):
            raise TypeError("LIVE_ACCEPTANCE_RUNNER_INVALID")
        self._authorizations = authorizations
        self._budget_binder = budget_binder
        self._runner = runner
        self._now = now
        self._completed: dict[tuple[str, str], tuple[str, LiveAcceptanceViewV1]] = {}
        self._pending: dict[tuple[str, str], _PendingEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def budget_binder(self) -> LiveAcceptanceBudgetBinder:
        """供组合根在挂载路由前验证生产持久化边界。"""

        return self._budget_binder

    async def execute(
        self, request: LiveAcceptanceRequestV1, *, tenant_id: str
    ) -> LiveAcceptanceViewV1:
        if not isinstance(request, LiveAcceptanceRequestV1):
            raise TypeError("LIVE_ACCEPTANCE_REQUEST_INVALID")
        if not tenant_id.strip() or len(tenant_id) > 128:
            raise LiveAcceptanceError("LIVE_TENANT_INVALID")
        authorization = self._validate_authorization(request, tenant_id=tenant_id)
        fingerprint = _request_fingerprint(request)
        key = (tenant_id, request.request_id)
        owner = False
        async with self._lock:
            completed = self._completed.get(key)
            if completed is not None:
                if completed[0] != fingerprint:
                    raise LiveAcceptanceError("LIVE_REQUEST_ID_CONFLICT")
                return completed[1]
            pending = self._pending.get(key)
            if pending is None:
                future = asyncio.get_running_loop().create_future()
                pending = _PendingEntry(fingerprint, future)
                self._pending[key] = pending
                owner = True
            elif pending.fingerprint != fingerprint:
                raise LiveAcceptanceError("LIVE_REQUEST_ID_CONFLICT")
        if not owner:
            return await asyncio.shield(pending.future)

        try:
            result = await self._execute_owned(
                request,
                authorization,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            async with self._lock:
                self._pending.pop(key, None)
                if not pending.future.done():
                    pending.future.set_exception(exc)
                    pending.future.exception()
            raise
        async with self._lock:
            self._pending.pop(key, None)
            self._completed[key] = (fingerprint, result)
            if not pending.future.done():
                pending.future.set_result(result)
        return result

    def _validate_authorization(
        self, request: LiveAcceptanceRequestV1, *, tenant_id: str
    ) -> LiveAcceptanceAuthorization:
        authorization = self._authorizations.get(request.authorization_id)
        observed_at = self._now()
        if observed_at.tzinfo is None:
            raise RuntimeError("LIVE_SERVER_CLOCK_NAIVE")
        if authorization is None:
            raise LiveAcceptanceError("LIVE_AUTHORIZATION_NOT_FOUND")
        if not authorization.approved_at <= observed_at < authorization.expires_at:
            raise LiveAcceptanceError("LIVE_AUTHORIZATION_EXPIRED")
        if tenant_id not in authorization.allowed_tenant_ids:
            raise LiveAcceptanceError("LIVE_TENANT_NOT_AUTHORIZED")
        if not _REQUIRED_ACTIONS.issubset(authorization.allowed_actions):
            raise LiveAcceptanceError("LIVE_ACTION_NOT_AUTHORIZED")
        if not set(request.case_ids).issubset(set(authorization.allowed_case_ids)):
            raise LiveAcceptanceError("LIVE_CASE_NOT_AUTHORIZED")
        if request.requested_budget_microunits > authorization.max_budget_microunits:
            raise LiveAcceptanceError("LIVE_BUDGET_NOT_AUTHORIZED")
        return authorization

    async def _execute_owned(
        self,
        request: LiveAcceptanceRequestV1,
        authorization: LiveAcceptanceAuthorization,
        *,
        tenant_id: str,
    ) -> LiveAcceptanceViewV1:
        binding = self._budget_binder.bind(
            authorization,
            request,
            tenant_id=tenant_id,
        )
        case_results: list[LiveAcceptanceCaseResultV1] = []
        reason_codes: tuple[str, ...] = ()
        try:
            for case_id in request.case_ids:
                raw = await self._runner.run_case(
                    case_id,
                    LIVE_ACCEPTANCE_CASE_PROMPTS[case_id],
                    binding,
                )
                item = LiveAcceptanceCaseResultV1.model_validate(raw)
                if item.case_id != case_id:
                    raise LiveAcceptanceError("LIVE_CASE_RESULT_MISMATCH")
                case_results.append(item)
                if case_id in _SOURCE_REQUIRED_CASES and not item.real_source_verified:
                    reason_codes = ("LIVE_SOURCE_NOT_VERIFIED",)
                    break
                if case_id in _MODEL_REQUIRED_CASES and not item.real_model_verified:
                    reason_codes = ("LIVE_MODEL_NOT_VERIFIED",)
                    break
        except BudgetLeaseError:
            reason_codes = ("LIVE_BUDGET_EXHAUSTED",)
        except LiveAcceptanceError as exc:
            reason_codes = (exc.reason_code,)
        except Exception:  # noqa: BLE001 - API 不泄露 Provider/Runner 异常
            reason_codes = ("LIVE_CASE_EXECUTION_FAILED",)
        finally:
            await binding.port.mark_scope_terminal(binding.scope, "terminal")
        snapshot = await binding.port.snapshot(binding.scope)
        status: Literal["PASS", "PARTIAL", "FAILED"]
        if reason_codes or any(item.status == "FAILED" for item in case_results):
            status = "FAILED"
        elif any(item.status == "PARTIAL" for item in case_results):
            status = "PARTIAL"
        else:
            status = "PASS"
        return LiveAcceptanceViewV1(
            request_id=request.request_id,
            authorization_id=authorization.authorization_id,
            acceptance_session_id=binding.lease_id,
            status=status,
            external_io=True,
            approved_budget_microunits=request.requested_budget_microunits,
            used_cost_microunits=snapshot.used.cost_microunits,
            case_results=tuple(case_results),
            reason_codes=reason_codes,
        )


def _request_fingerprint(request: LiveAcceptanceRequestV1) -> str:
    payload = request.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _has_citations(value: object) -> bool:
    if isinstance(value, Mapping):
        citations = value.get("citations")
        if isinstance(citations, list) and any(
            isinstance(item, Mapping)
            and isinstance(item.get("url"), str)
            and item["url"].startswith("https://")
            for item in citations
        ):
            return True
        return any(_has_citations(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_citations(item) for item in value)
    return False


__all__ = [
    "ConversationLiveAcceptanceRunner",
    "InMemoryLiveAcceptanceAuthorizationStore",
    "InMemoryLiveAcceptanceBudgetBinder",
    "JsonLiveAcceptanceAuthorizationStore",
    "LiveAcceptanceAuthorization",
    "LiveAcceptanceBudgetBinder",
    "LiveAcceptanceBudgetBinding",
    "LiveAcceptanceCaseRunner",
    "LiveAcceptanceError",
    "LiveAcceptanceService",
    "PostgresLiveAcceptanceBudgetBinder",
]
