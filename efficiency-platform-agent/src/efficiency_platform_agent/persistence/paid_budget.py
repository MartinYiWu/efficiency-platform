from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, replace
from functools import wraps
from pathlib import Path
from typing import Any

from efficiency_platform_agent.core.execution_control import (
    MAX_RUN_CALLS,
    MAX_RUN_COST_MICROUNITS,
    MAX_RUN_DURATION_MS,
)
from efficiency_platform_agent.core.memory import ConversationScope
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
    PaidReservation,
    PaidUsage,
    PaidWorkloadItem,
    _pos,
    calculate_paid_cost,
)
from efficiency_platform_agent.core.task_authorization import (
    TaskContinuation,
    TaskPaidBinding,
)


def _execution_identity(
    tenant_id: str, scope: ConversationScope | None
) -> bytes | None:
    """完整可信作用域按原字符串精确绑定，不折叠大小写、空格或Unicode。"""
    if scope is None:
        return None
    if not isinstance(scope, ConversationScope) or scope.tenant_id != tenant_id:
        raise PaidBudgetError("HR_EXECUTION_SCOPE_CONFLICT", "execution scope mismatch")
    return json.dumps(
        asdict(scope), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _closed(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return method(*args, **kwargs)
        except (
            sqlite3.Error,
            OSError,
            ValueError,
            OverflowError,
            TypeError,
            KeyError,
            IndexError,
        ):
            raise PaidBudgetError(
                "LEDGER_UNAVAILABLE", "paid budget ledger unavailable"
            ) from None

    return invoke


class SqlitePaidBudgetLedger:
    @_closed
    def initialize_task_authorization_schema(self, backup_path: Path) -> None:
        """仅本机显式迁移入口：先SQLite一致性备份，再建表并核验；构造器不调用。"""
        target = Path(backup_path).resolve()
        if self.read_only or target == self.path or target.exists():
            raise PaidBudgetError(
                "TASK_SCHEMA_BACKUP_REQUIRED", "new backup path required"
            )
        with closing(self._db()) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise PaidBudgetError(
                    "LEDGER_UNAVAILABLE", "ledger integrity check failed"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb"):
                pass
            with closing(sqlite3.connect(target)) as backup:
                connection.backup(backup)
                if backup.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise PaidBudgetError(
                        "LEDGER_UNAVAILABLE", "backup verification failed"
                    )
            connection.executescript(
                "BEGIN IMMEDIATE;"
                "CREATE TABLE IF NOT EXISTS task_budget_chains(task TEXT PRIMARY KEY,chain TEXT NOT NULL UNIQUE,root_bid TEXT NOT NULL UNIQUE,limits TEXT NOT NULL,identity BLOB NOT NULL,operation_limit INTEGER NOT NULL);"
                "CREATE TABLE IF NOT EXISTS task_authorizations(id TEXT PRIMARY KEY,chain TEXT NOT NULL,parent TEXT,request_hash TEXT UNIQUE,run TEXT,identity BLOB NOT NULL);"
                "CREATE TABLE IF NOT EXISTS task_paid_operations(chain TEXT NOT NULL,operation TEXT NOT NULL,input_hash TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(chain,operation));"
                "CREATE TABLE IF NOT EXISTS task_authorization_schema(version INTEGER PRIMARY KEY CHECK(version=1));"
                "INSERT OR IGNORE INTO task_authorization_schema VALUES(1);COMMIT;"
            )
            self._task_schema(connection)

    def _task_schema(self, connection: sqlite3.Connection) -> None:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_authorization_schema'"
        ).fetchone():
            raise PaidBudgetError(
                "TASK_SCHEMA_REQUIRED", "reviewed task schema required"
            )
        row = connection.execute(
            "SELECT version FROM task_authorization_schema"
        ).fetchall()
        if row != [(1,)]:
            raise PaidBudgetError(
                "TASK_SCHEMA_REQUIRED", "reviewed task schema required"
            )

    def _task_totals(
        self, connection: sqlite3.Connection, chain: str
    ) -> dict[str, int]:
        totals = connection.execute(
            "SELECT COALESCE(SUM(b.calls),0),COALESCE(SUM(b.cost),0),COALESCE(SUM(b.inflight),0) FROM budgets b JOIN task_authorizations a ON a.id=b.id WHERE a.chain=?",
            (chain,),
        ).fetchone()
        result = dict(zip(("calls", "cost_microunits", "inflight"), totals))
        result.update(input_tokens=0, output_tokens=0, reasoning_tokens=0)
        for (
            held_input,
            held_output,
            held_reasoning,
            encoded,
            state,
        ) in connection.execute(
            "SELECT r.reserved_input,r.reserved_output,r.reserved_reasoning,r.usage,r.state FROM reservations r JOIN task_authorizations a ON a.id=r.bid WHERE a.chain=?",
            (chain,),
        ):
            usage = json.loads(encoded) if encoded else None
            for dimension, held in zip(
                ("input", "output", "reasoning"),
                (held_input, held_output, held_reasoning),
            ):
                if held is None:
                    raise PaidBudgetError(
                        "TASK_HISTORY_UNVERIFIED", "legacy token bounds unavailable"
                    )
                amount = usage[dimension + "_tokens"] if usage else held
                result[dimension + "_tokens"] += (
                    max(held, amount) if state == "anomaly" else amount
                )
        return result

    def _task_provider_check(
        self, connection: sqlite3.Connection, providers: set[str], threshold: int
    ) -> None:
        # 供应商账户在本机总账共享；新授权不能抹去旧402及累计429熔断。
        for provider in providers:
            statuses = connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN status=402 THEN 1 ELSE 0 END),0),COALESCE(SUM(CASE WHEN status=429 THEN 1 ELSE 0 END),0) FROM reservations WHERE provider=?",
                (provider,),
            ).fetchone()
            stopped = connection.execute(
                "SELECT 1 FROM budgets b JOIN prices p ON p.bid=b.id WHERE p.provider=? AND b.stopped IN ('402','429','usage_overflow','usage_exceeded') LIMIT 1",
                (provider,),
            ).fetchone()
            if stopped or statuses[0] or statuses[1] >= threshold:
                raise PaidBudgetError(
                    "PROVIDER_CIRCUIT_OPEN", "provider circuit is permanently open"
                )

    def _task_reserve(
        self,
        connection: sqlite3.Connection,
        bid: str,
        binding: TaskPaidBinding | None,
        price: PaidPriceLimit,
        requested: tuple[int, int, int],
        now: int,
    ) -> int | None:
        if not self.task_authorization_enabled:
            if binding is not None:
                raise PaidBudgetError(
                    "CONTINUATION_AUTH_UNSUPPORTED", "task authorization disabled"
                )
            if (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_authorizations'"
                ).fetchone()
                and connection.execute(
                    "SELECT 1 FROM task_authorizations WHERE id=?", (bid,)
                ).fetchone()
            ):
                raise PaidBudgetError(
                    "CONTINUATION_AUTH_UNSUPPORTED", "task authorization disabled"
                )
            return None
        self._task_schema(connection)
        if binding is None:
            # 一旦budget属于task，所有通道都必须携带同一可信身份。
            if connection.execute(
                "SELECT 1 FROM task_authorizations WHERE id=?", (bid,)
            ).fetchone():
                raise PaidBudgetError(
                    "TASK_SCOPE_REQUIRED", "trusted task binding required"
                )
            return None
        scope = binding.scope
        identity = _execution_identity(scope.conversation.tenant_id, scope.conversation)
        root = connection.execute(
            "SELECT chain,root_bid,limits,identity,operation_limit FROM task_budget_chains WHERE task=?",
            (scope.task_id,),
        ).fetchone()
        plan = PaidBudgetPlan(
            **json.loads(
                connection.execute(
                    "SELECT plan FROM budgets WHERE id=?", (bid,)
                ).fetchone()[0]
            )
        )
        if root is None:
            if connection.execute(
                "SELECT 1 FROM reservations WHERE bid=? LIMIT 1", (bid,)
            ).fetchone():
                raise PaidBudgetError(
                    "TASK_HISTORY_UNVERIFIED",
                    "legacy operations cannot be assigned to task automatically",
                )
            if connection.execute(
                "SELECT 1 FROM task_authorizations WHERE id=?", (bid,)
            ).fetchone():
                raise PaidBudgetError(
                    "TASK_SCOPE_CONFLICT", "authorization belongs to another task"
                )
            chain = hashlib.sha256((scope.task_id + "\0" + bid).encode()).hexdigest()
            limits = {
                "max_total_http": min(
                    plan.max_calls, plan.max_run_calls, MAX_RUN_CALLS
                ),
                "max_total_cost_microunits": min(
                    plan.max_cost_microunits,
                    plan.max_run_cost_microunits,
                    MAX_RUN_COST_MICROUNITS,
                ),
                "max_input_tokens": min(
                    plan.max_input_tokens, plan.max_run_input_tokens
                ),
                "max_output_tokens": min(
                    plan.max_output_tokens, plan.max_run_output_tokens
                ),
                "max_reasoning_tokens": min(
                    plan.max_reasoning_tokens, plan.max_run_reasoning_tokens
                ),
            }
            run_limit = connection.execute(
                "SELECT operation_attempt_limit FROM execution_runs WHERE tenant=? AND run=?",
                (scope.conversation.tenant_id, scope.execution_id),
            ).fetchone()
            operation_limit = min(3, run_limit[0]) if run_limit else 3
            connection.execute(
                "INSERT INTO task_budget_chains VALUES(?,?,?,?,?,?)",
                (
                    scope.task_id,
                    chain,
                    bid,
                    json.dumps(limits),
                    identity,
                    operation_limit,
                ),
            )
            connection.execute(
                "INSERT INTO task_authorizations(id,chain,run,identity) VALUES(?,?,?,?)",
                (bid, chain, scope.execution_id, identity),
            )
            root = chain, bid, json.dumps(limits), identity, operation_limit
        if root[3] != identity:
            raise PaidBudgetError(
                "TASK_SCOPE_CONFLICT", "task conversation identity changed"
            )
        authorization = connection.execute(
            "SELECT chain,run,identity FROM task_authorizations WHERE id=?", (bid,)
        ).fetchone()
        if (
            not authorization
            or authorization[0] != root[0]
            or authorization[2] != identity
        ):
            raise PaidBudgetError(
                "TASK_AUTHORIZATION_REQUIRED", "authorization not bound to task"
            )
        if authorization[1] not in (None, scope.execution_id):
            raise PaidBudgetError(
                "TASK_RUN_CONFLICT", "authorization already bound to another execution"
            )
        connection.execute(
            "UPDATE task_authorizations SET run=COALESCE(run,?) WHERE id=?",
            (scope.execution_id, bid),
        )
        # 后继预算绑定新run；绝不更新/延长旧run的截止或stopped。
        run = connection.execute(
            "SELECT deadline,stopped,context_identity FROM execution_runs WHERE tenant=? AND run=?",
            (scope.conversation.tenant_id, scope.execution_id),
        ).fetchone()
        deadline = min(
            plan.deadline_epoch_ms,
            now + min(plan.max_run_duration_ms, MAX_RUN_DURATION_MS),
        )
        if run:
            if run[1] or now >= run[0] or run[2] != identity:
                raise PaidBudgetError(
                    "AGENT_TASK_STOPPED", "execution stopped or identity changed"
                )
            deadline = min(deadline, run[0])
        else:
            connection.execute(
                "INSERT INTO execution_runs(tenant,run,deadline,context_identity) VALUES(?,?,?,?)",
                (scope.conversation.tenant_id, scope.execution_id, deadline, identity),
            )
        limits = json.loads(root[2])
        totals = self._task_totals(connection, root[0])
        self._task_provider_check(connection, {price.provider}, plan.max_429_responses)
        if (
            totals["calls"] + 1 > limits["max_total_http"]
            or totals["cost_microunits"] + price.max_cost_microunits_per_attempt
            > limits["max_total_cost_microunits"]
            or any(
                totals[dimension + "_tokens"] + amount
                > limits["max_" + dimension + "_tokens"]
                for dimension, amount in zip(
                    ("input", "output", "reasoning"), requested
                )
            )
        ):
            raise PaidBudgetError(
                "TASK_BUDGET_EXHAUSTED", "task cumulative budget exhausted"
            )
        operation = connection.execute(
            "SELECT input_hash,attempts FROM task_paid_operations WHERE chain=? AND operation=?",
            (root[0], binding.operation_id),
        ).fetchone()
        if operation and operation[0] != binding.input_hash:
            raise PaidBudgetError(
                "TASK_OPERATION_INPUT_CONFLICT", "operation input changed"
            )
        if operation and operation[1] >= root[4]:
            raise PaidBudgetError(
                "AGENT_OPERATION_ATTEMPTS_EXHAUSTED",
                "task operation attempts exhausted",
            )
        connection.execute(
            "INSERT INTO task_paid_operations(chain,operation,input_hash,attempts) VALUES(?,?,?,1) ON CONFLICT(chain,operation) DO UPDATE SET attempts=attempts+1",
            (root[0], binding.operation_id, binding.input_hash),
        )
        return deadline

    @_closed
    def task_authorization_snapshot(self, task_id: str) -> dict[str, Any]:
        with closing(self._db()) as connection:
            connection.execute("BEGIN")
            self._task_schema(connection)
            row = connection.execute(
                "SELECT chain,root_bid,limits FROM task_budget_chains WHERE task=?",
                (task_id,),
            ).fetchone()
            if not row:
                raise PaidBudgetError(
                    "TASK_AUTHORIZATION_REQUIRED", "task has no original authorization"
                )
            return {
                "task_id": task_id,
                "chain_id": row[0],
                "root_authorization_id": row[1],
                "limits": json.loads(row[2]),
                **self._task_totals(connection, row[0]),
            }

    @_closed
    def task_budget_id(
        self, binding: TaskPaidBinding, fallback: str | None
    ) -> str | None:
        with closing(self._db()) as connection:
            self._task_schema(connection)
            row = connection.execute(
                "SELECT a.id FROM task_authorizations a JOIN task_budget_chains c ON c.chain=a.chain WHERE c.task=? AND a.run=?",
                (binding.scope.task_id, binding.scope.execution_id),
            ).fetchone()
            if row:
                return row[0]
            row = connection.execute(
                "SELECT a.id FROM task_authorizations a JOIN task_budget_chains c ON c.chain=a.chain WHERE c.task=? AND a.run IS NULL ORDER BY a.rowid DESC LIMIT 1",
                (binding.scope.task_id,),
            ).fetchone()
            return row[0] if row else fallback

    @_closed
    def authorize_task_continuation(
        self,
        request: TaskContinuation,
        prices: tuple[PaidPriceLimit, ...],
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not self.task_authorization_enabled:
            raise PaidBudgetError(
                "CONTINUATION_AUTH_UNSUPPORTED", "task authorization disabled"
            )
        # 共用原authorize的价格/最坏成本验证；不另开总账或临时授权。
        self._validate_prices(prices)
        with closing(self._db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE" if confirm else "BEGIN")
            self._task_schema(connection)
            parent = connection.execute(
                "SELECT a.chain,c.limits,c.identity,b.plan,b.stopped,a.run FROM task_authorizations a JOIN task_budget_chains c ON c.chain=a.chain JOIN budgets b ON b.id=a.id WHERE a.id=? AND c.task=?",
                (request.continuation_of, request.task_id),
            ).fetchone()
            if not parent:
                raise PaidBudgetError(
                    "TASK_AUTHORIZATION_REQUIRED", "parent authorization not in task"
                )
            previous = PaidBudgetPlan(**json.loads(parent[3]))
            limits = json.loads(parent[1])
            for key in limits:
                if getattr(request, key) > limits[key]:
                    raise PaidBudgetError(
                        "TASK_LIMIT_EXPANSION",
                        "continuation cannot increase task limits",
                    )
            canonical = json.dumps(
                {
                    "request": asdict(request),
                    "prices": sorted(
                        (asdict(p) for p in prices),
                        key=lambda p: (p["provider"], p["model"]),
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            request_hash = hashlib.sha256(canonical.encode()).hexdigest()
            authorization_id = "task-auth-" + request_hash
            existing = connection.execute(
                "SELECT id FROM task_authorizations WHERE request_hash=?",
                (request_hash,),
            ).fetchone()
            result = {
                "task_id": request.task_id,
                "chain_id": parent[0],
                "authorization_id": authorization_id,
                "continuation_of": request.continuation_of,
                "limits": {key: getattr(request, key) for key in limits},
                "expires_at_epoch_ms": request.expires_at_epoch_ms,
            }
            if existing:
                return result
            now = int(time.time() * 1000)
            if not now < request.expires_at_epoch_ms <= now + MAX_RUN_DURATION_MS:
                raise PaidBudgetError(
                    "INVALID_PLAN", "continuation window must be within ten minutes"
                )
            if not parent[4] and now < previous.deadline_epoch_ms:
                raise PaidBudgetError(
                    "TASK_AUTHORIZATION_ACTIVE", "parent authorization is still active"
                )
            if connection.execute(
                "SELECT 1 FROM task_authorizations WHERE parent=?",
                (request.continuation_of,),
            ).fetchone():
                raise PaidBudgetError(
                    "TASK_CONTINUATION_CONFLICT", "parent already has a successor"
                )
            root_models = {
                (r[0], r[1])
                for r in connection.execute(
                    "SELECT p.provider,p.model FROM prices p JOIN task_budget_chains c ON c.root_bid=p.bid WHERE c.chain=?",
                    (parent[0],),
                )
            }
            if any((p.provider, p.model) not in root_models for p in prices):
                raise PaidBudgetError(
                    "UNKNOWN_PRICE", "continuation model outside original authorization"
                )
            self._task_provider_check(
                connection, {p.provider for p in prices}, previous.max_429_responses
            )
            totals = self._task_totals(connection, parent[0])
            if (
                totals["calls"] >= request.max_total_http
                or totals["cost_microunits"] >= request.max_total_cost_microunits
                or any(
                    totals[d + "_tokens"] > getattr(request, "max_" + d + "_tokens")
                    for d in ("input", "output", "reasoning")
                )
            ):
                raise PaidBudgetError(
                    "TASK_BUDGET_EXHAUSTED", "task cumulative budget exhausted"
                )
            if confirm:
                plan = replace(
                    previous,
                    budget_id=authorization_id,
                    max_calls=request.max_total_http,
                    max_cost_microunits=request.max_total_cost_microunits,
                    deadline_epoch_ms=request.expires_at_epoch_ms,
                    max_run_calls=min(previous.max_run_calls, request.max_total_http),
                    max_run_cost_microunits=min(
                        previous.max_run_cost_microunits,
                        request.max_total_cost_microunits,
                    ),
                    max_input_tokens=request.max_input_tokens,
                    max_output_tokens=request.max_output_tokens,
                    max_reasoning_tokens=request.max_reasoning_tokens,
                    max_run_input_tokens=min(
                        previous.max_run_input_tokens, request.max_input_tokens
                    ),
                    max_run_output_tokens=min(
                        previous.max_run_output_tokens, request.max_output_tokens
                    ),
                    max_run_reasoning_tokens=min(
                        previous.max_run_reasoning_tokens, request.max_reasoning_tokens
                    ),
                )
                connection.execute(
                    "UPDATE budgets SET stopped=COALESCE(stopped,'expired') WHERE id=?",
                    (request.continuation_of,),
                )
                if parent[5] is not None:
                    tenant = json.loads(parent[2])["tenant_id"]
                    connection.execute(
                        "UPDATE execution_runs SET stopped=COALESCE(stopped,'expired') WHERE tenant=? AND run=?",
                        (tenant, parent[5]),
                    )
                connection.execute(
                    "INSERT INTO budgets(id,plan) VALUES(?,?)",
                    (authorization_id, json.dumps(asdict(plan))),
                )
                connection.executemany(
                    "INSERT INTO prices(bid,provider,model,req,out,cost,src,pricing) VALUES(?,?,?,?,?,?,?,?)",
                    [
                        (
                            authorization_id,
                            p.provider,
                            p.model,
                            p.max_request_bytes,
                            p.max_output_tokens,
                            p.max_cost_microunits_per_attempt,
                            p.pricing_source,
                            json.dumps(asdict(p)),
                        )
                        for p in prices
                    ],
                )
                connection.execute(
                    "INSERT INTO task_authorizations(id,chain,parent,request_hash,identity) VALUES(?,?,?,?,?)",
                    (
                        authorization_id,
                        parent[0],
                        request.continuation_of,
                        request_hash,
                        parent[2],
                    ),
                )
                connection.execute(
                    "UPDATE task_budget_chains SET limits=? WHERE chain=?",
                    (json.dumps(result["limits"]), parent[0]),
                )
            return result

    @_closed
    def __init__(
        self,
        path: Path,
        *,
        read_only: bool = False,
        task_authorization_enabled: bool = False,
    ) -> None:
        if type(task_authorization_enabled) is not bool:
            raise PaidBudgetError(
                "INVALID_PLAN", "explicit task authorization feature flag required"
            )
        self._task_authorization_enabled = task_authorization_enabled
        self.path = Path(path).resolve()
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init()

    @property
    def task_authorization_enabled(self) -> bool:
        return self._task_authorization_enabled

    def _db(self) -> sqlite3.Connection:
        c = (
            sqlite3.connect(
                self.path.as_uri() + "?mode=ro",
                uri=True,
                timeout=10,
                isolation_level=None,
            )
            if self.read_only
            else sqlite3.connect(self.path, timeout=10, isolation_level=None)
        )
        c.execute("PRAGMA busy_timeout=10000")
        return c

    def _init(self) -> None:
        c = self._db()
        c.executescript(
            "CREATE TABLE IF NOT EXISTS scopes(bid TEXT,scope TEXT,calls INTEGER DEFAULT 0,cost INTEGER DEFAULT 0,deadline INTEGER,stopped INTEGER DEFAULT 0,PRIMARY KEY(bid,scope)); CREATE TABLE IF NOT EXISTS budgets (id TEXT PRIMARY KEY, plan TEXT NOT NULL, calls INTEGER DEFAULT 0,cost INTEGER DEFAULT 0,run_calls INTEGER DEFAULT 0,run_cost INTEGER DEFAULT 0,inflight INTEGER DEFAULT 0,stopped TEXT, r429 INTEGER DEFAULT 0, first_ms INTEGER); CREATE TABLE IF NOT EXISTS prices (bid TEXT,provider TEXT,model TEXT,req INTEGER,out INTEGER,cost INTEGER,src TEXT,PRIMARY KEY(bid,provider,model)); CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY,bid TEXT,scope TEXT,deadline INTEGER,active INTEGER DEFAULT 1,status INTEGER)"
        )
        c.executescript(
            "CREATE TABLE IF NOT EXISTS execution_runs(tenant TEXT,run TEXT,deadline INTEGER NOT NULL,stopped TEXT,calls INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant,run));"
            "CREATE TABLE IF NOT EXISTS execution_operations(tenant TEXT,run TEXT,operation TEXT,input_hash TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant,run,operation));"
        )
        c.executescript(
            "CREATE TABLE IF NOT EXISTS workload_plans(id TEXT PRIMARY KEY,bid TEXT NOT NULL,input_hash TEXT NOT NULL,max_calls INTEGER NOT NULL,max_cost INTEGER NOT NULL,max_input INTEGER NOT NULL,max_output INTEGER NOT NULL,max_reasoning INTEGER NOT NULL,deadline INTEGER NOT NULL,calls INTEGER NOT NULL DEFAULT 0,cost INTEGER NOT NULL DEFAULT 0,stopped TEXT);"
            "CREATE TABLE IF NOT EXISTS workload_plan_scopes(plan_id TEXT NOT NULL,bid TEXT NOT NULL,scope TEXT NOT NULL,PRIMARY KEY(bid,scope));"
        )
        c.execute("BEGIN IMMEDIATE")
        for table, columns in {
            "execution_runs": {
                "operation_attempt_limit": "INTEGER NOT NULL DEFAULT 3",
                "context_identity": "BLOB",
            },
            "prices": {"pricing": "TEXT"},
            "reservations": {
                "provider": "TEXT",
                "model": "TEXT",
                "reserved_input": "INTEGER",
                "reserved_output": "INTEGER",
                "reserved_reasoning": "INTEGER",
                "reserved_cost": "INTEGER",
                "pricing": "TEXT",
                "usage": "TEXT",
                "actual_cost": "INTEGER",
                "actual_cost_decimal": "TEXT",
                "state": "TEXT DEFAULT 'legacy'",
            },
        }.items():
            existing = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            for name, kind in columns.items():
                if name not in existing:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        c.commit()
        c.close()

    @_closed
    def bind_execution(
        self,
        tenant_id: str,
        run_id: str,
        duration_ms: int,
        maximum_attempts: int = 3,
        *,
        context_scope: ConversationScope | None = None,
    ) -> int:
        if (
            not tenant_id
            or not run_id
            or not 0 < duration_ms <= MAX_RUN_DURATION_MS
            or isinstance(maximum_attempts, bool)
            or not 1 <= maximum_attempts <= 3
        ):
            raise PaidBudgetError("INVALID_EXECUTION", "invalid execution binding")
        identity = _execution_identity(tenant_id, context_scope)
        with closing(self._db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            now = int(time.time() * 1000)
            connection.execute(
                "INSERT INTO execution_runs(tenant,run,deadline,operation_attempt_limit,context_identity) VALUES (?,?,?,?,?) ON CONFLICT(tenant,run) DO NOTHING",
                (tenant_id, run_id, now + duration_ms, maximum_attempts, identity),
            )
            row = connection.execute(
                "SELECT deadline,stopped,context_identity FROM execution_runs WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            ).fetchone()
            if row[2] != identity:
                raise PaidBudgetError(
                    "HR_EXECUTION_SCOPE_CONFLICT", "execution scope mismatch"
                )
            if row[1] or now >= row[0]:
                raise PaidBudgetError("AGENT_TASK_STOPPED", "task stopped or expired")
            return int(row[0])

    @_closed
    def execution_attempt_limit(self, tenant_id: str, run_id: str) -> int:
        with closing(self._db()) as connection:
            row = connection.execute(
                "SELECT operation_attempt_limit FROM execution_runs WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            ).fetchone()
            if not row or not 1 <= row[0] <= 3:
                raise PaidBudgetError(
                    "INVALID_EXECUTION", "frozen attempt limit unavailable"
                )
            return int(row[0])

    @_closed
    def check_execution(self, tenant_id: str, run_id: str) -> None:
        with closing(self._db()) as connection, connection:
            row = connection.execute(
                "SELECT deadline,stopped FROM execution_runs WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            ).fetchone()
            if not row or row[1] or int(time.time() * 1000) >= row[0]:
                raise PaidBudgetError("AGENT_TASK_STOPPED", "task stopped or expired")

    @_closed
    def stop_execution(
        self,
        tenant_id: str,
        run_id: str,
        code: str = "AGENT_TASK_STOPPED",
        *,
        context_scope: ConversationScope | None = None,
    ) -> None:
        identity = _execution_identity(tenant_id, context_scope)
        with closing(self._db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT context_identity FROM execution_runs WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            ).fetchone()
            if row is not None and row[0] != identity:
                raise PaidBudgetError(
                    "HR_EXECUTION_SCOPE_CONFLICT", "execution scope mismatch"
                )
            connection.execute(
                "UPDATE execution_runs SET stopped=COALESCE(stopped,?) WHERE tenant=? AND run=?",
                (code, tenant_id, run_id),
            )

    @_closed
    def claim_execution_operation(
        self, tenant_id: str, run_id: str, operation_id: str, input_hash: str
    ) -> bool:
        self.check_execution(tenant_id, run_id)
        with closing(self._db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT input_hash FROM execution_operations WHERE tenant=? AND run=? AND operation=?",
                (tenant_id, run_id, operation_id),
            ).fetchone()
            if row:
                if row[0] != input_hash:
                    raise PaidBudgetError(
                        "HR_OPERATION_INPUT_CONFLICT", "operation input changed"
                    )
                return False
            connection.execute(
                "INSERT INTO execution_operations(tenant,run,operation,input_hash) VALUES(?,?,?,?)",
                (tenant_id, run_id, operation_id, input_hash),
            )
            return True

    @_closed
    def consume_execution_attempt(
        self, tenant_id: str, run_id: str, operation_id: str
    ) -> None:
        with closing(self._db()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT deadline,stopped,calls,operation_attempt_limit FROM execution_runs WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            ).fetchone()
            if not row or row[1] or int(time.time() * 1000) >= row[0]:
                raise PaidBudgetError("AGENT_TASK_STOPPED", "task stopped or expired")
            operation = connection.execute(
                "SELECT attempts FROM execution_operations WHERE tenant=? AND run=? AND operation=?",
                (tenant_id, run_id, operation_id),
            ).fetchone()
            attempts = operation[0] if operation else 0
            code = (
                "AGENT_OPERATION_ATTEMPTS_EXHAUSTED"
                if attempts >= min(3, row[3])
                else "AGENT_CALL_LIMIT_EXCEEDED"
                if row[2] >= MAX_RUN_CALLS
                else None
            )
            if code:
                connection.execute(
                    "UPDATE execution_runs SET stopped=? WHERE tenant=? AND run=?",
                    (code, tenant_id, run_id),
                )
                connection.commit()
                raise PaidBudgetError(code, "execution attempts exhausted")
            connection.execute(
                "INSERT INTO execution_operations(tenant,run,operation,input_hash,attempts) VALUES(?,?,?,'unbound',1) ON CONFLICT(tenant,run,operation) DO UPDATE SET attempts=attempts+1",
                (tenant_id, run_id, operation_id),
            )
            connection.execute(
                "UPDATE execution_runs SET calls=calls+1 WHERE tenant=? AND run=?",
                (tenant_id, run_id),
            )

    @_closed
    def authorize(
        self, plan: PaidBudgetPlan, prices: tuple[PaidPriceLimit, ...]
    ) -> None:
        if not prices or any(
            getattr(plan, k) <= 0
            for k in (
                "max_calls",
                "max_cost_microunits",
                "max_run_calls",
                "max_run_cost_microunits",
                "max_run_duration_ms",
                "max_inflight",
                "max_429_responses",
            )
        ):
            raise PaidBudgetError("INVALID_PLAN", "positive authorization required")
        if plan.max_input_tokens <= 0 or plan.max_run_input_tokens <= 0:
            raise PaidBudgetError(
                "INVALID_PLAN", "explicit token authorization required"
            )
        self._validate_prices(prices)
        c = self._db()
        try:
            c.execute("BEGIN IMMEDIATE")
            if c.execute(
                "SELECT 1 FROM budgets WHERE id=?", (plan.budget_id,)
            ).fetchone():
                raise PaidBudgetError("BUDGET_EXISTS", "budget id already exists")

            if self.task_authorization_enabled:
                self._task_schema(c)
                self._task_provider_check(
                    c, {p.provider for p in prices}, plan.max_429_responses
                )
            c.execute("UPDATE budgets SET stopped='superseded' WHERE stopped IS NULL")
            c.execute(
                "INSERT INTO budgets(id,plan) VALUES (?,?)",
                (plan.budget_id, json.dumps(plan.__dict__)),
            )
            c.executemany(
                "INSERT INTO prices(bid,provider,model,req,out,cost,src,pricing) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        plan.budget_id,
                        p.provider,
                        p.model,
                        p.max_request_bytes,
                        p.max_output_tokens,
                        p.max_cost_microunits_per_attempt,
                        p.pricing_source,
                        json.dumps(p.__dict__),
                    )
                    for p in prices
                ],
            )
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def _validate_prices(self, prices: tuple[PaidPriceLimit, ...]) -> None:
        if not prices or len({(p.provider, p.model) for p in prices}) != len(prices):
            raise PaidBudgetError("INVALID_PRICE", "unique verified prices required")
        for price in prices:
            if (
                not price.pricing_version.strip()
                or price.max_input_tokens <= 0
                or price.input_microunits_per_million <= 0
                or (
                    price.provider == "deepseek"
                    and price.output_microunits_per_million <= 0
                )
            ):
                raise PaidBudgetError(
                    "INVALID_PRICE", "verified token pricing required"
                )
            worst = calculate_paid_cost(
                PaidUsage(price.max_input_tokens, price.max_output_tokens), price
            )
            cached_worst = calculate_paid_cost(
                PaidUsage(
                    price.max_input_tokens,
                    price.max_output_tokens,
                    price.max_input_tokens,
                ),
                price,
            )
            if max(worst, cached_worst) > price.max_cost_microunits_per_attempt:
                raise PaidBudgetError(
                    "INVALID_PRICE", "attempt cost cap below worst case"
                )

    @_closed
    def active_budget_id(self) -> str | None:
        c = self._db()
        r = c.execute("SELECT id FROM budgets ORDER BY rowid DESC LIMIT 1").fetchone()
        c.close()
        return r[0] if r else None

    @_closed
    def check_workload(
        self,
        requirements: list[PaidWorkloadItem],
        expected_budget_ref: str | None = None,
        expected_plan_ref: str | None = None,
    ) -> dict[str, object]:
        """同一写锁内核实整批最坏调用/金额/Token；不授权、不续期、不清零。"""
        if len(requirements) > 1700:
            raise PaidBudgetError("INVALID_WORKLOAD", "workload too large")
        if (
            not requirements
            and expected_budget_ref is None
            and expected_plan_ref is None
        ):
            return {"maximum_calls": 0, "maximum_cost_microunits": 0, "ready": True}
        with closing(self._db()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT id,plan,calls,cost,stopped FROM budgets ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if not row:
                raise PaidBudgetError("NO_BUDGET", "no active budget")
            bid, encoded, used_calls, used_cost, stopped = row
            if expected_budget_ref is not None and bid != expected_budget_ref:
                raise PaidBudgetError(
                    "BUDGET_REFERENCE_CHANGED",
                    "frozen budget reference no longer active",
                )
            if expected_plan_ref is not None:
                frozen = c.execute(
                    "SELECT id,bid,max_calls,max_cost,deadline,calls,cost,stopped FROM workload_plans WHERE id=?",
                    (expected_plan_ref,),
                ).fetchone()
                if (
                    not frozen
                    or frozen[1] != bid
                    or frozen[7]
                    or int(time.time() * 1000) >= frozen[4]
                    or frozen[5] >= frozen[2]
                    or frozen[6] >= frozen[3]
                ):
                    raise PaidBudgetError(
                        "WORKLOAD_PLAN_EXHAUSTED",
                        "frozen workload plan stopped or exhausted",
                    )
            plan = PaidBudgetPlan(**json.loads(encoded))
            task_totals = None
            if c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_authorizations'"
            ).fetchone():
                chain = c.execute(
                    "SELECT a.chain,c.limits FROM task_authorizations a JOIN task_budget_chains c ON c.chain=a.chain WHERE a.id=?",
                    (bid,),
                ).fetchone()
                if chain:
                    if not self.task_authorization_enabled:
                        raise PaidBudgetError(
                            "CONTINUATION_AUTH_UNSUPPORTED",
                            "task authorization disabled",
                        )
                    self._task_provider_check(
                        c, {w.provider for w in requirements}, plan.max_429_responses
                    )
                    task_totals = self._task_totals(c, chain[0])
                    task_limits = json.loads(chain[1])
                    used_calls, used_cost = (
                        task_totals["calls"],
                        task_totals["cost_microunits"],
                    )
                    plan = replace(
                        plan,
                        max_calls=min(plan.max_calls, task_limits["max_total_http"]),
                        max_cost_microunits=min(
                            plan.max_cost_microunits,
                            task_limits["max_total_cost_microunits"],
                        ),
                    )
            now = int(time.time() * 1000)
            if stopped or now >= plan.deadline_epoch_ms:
                raise PaidBudgetError("BUDGET_STOPPED", "budget stopped or expired")
            calls = cost = 0
            tokens = {"input": 0, "output": 0, "reasoning": 0}
            by_scope: dict[str, dict[str, int]] = {}
            for work in requirements:
                if not isinstance(work, PaidWorkloadItem):
                    raise PaidBudgetError("INVALID_WORKLOAD", "invalid workload item")
                price = c.execute(
                    "SELECT req,out,cost,pricing FROM prices WHERE bid=? AND provider=? AND model=?",
                    (bid, work.provider, work.model),
                ).fetchone()
                if not price or not price[3]:
                    raise PaidBudgetError("UNKNOWN_PRICE", "verified price unavailable")
                frozen = PaidPriceLimit(**json.loads(price[3]))
                if (
                    not frozen.pricing_version
                    or frozen.input_microunits_per_million <= 0
                    or work.request_bytes > price[0]
                    or work.output_tokens > price[1]
                    or work.input_tokens > frozen.max_input_tokens
                ):
                    raise PaidBudgetError(
                        "PAYLOAD_LIMIT", "workload exceeds verified price bounds"
                    )
                worst = max(
                    calculate_paid_cost(
                        PaidUsage(work.input_tokens, work.output_tokens), frozen
                    ),
                    calculate_paid_cost(
                        PaidUsage(
                            work.input_tokens, work.output_tokens, work.input_tokens
                        ),
                        frozen,
                    ),
                )
                if worst > price[2]:
                    raise PaidBudgetError(
                        "INVALID_PRICE", "attempt cost below worst case"
                    )
                calls += work.attempts
                cost += work.attempts * price[2]
                scope = by_scope.setdefault(
                    work.scope_id,
                    {"calls": 0, "cost": 0, "input": 0, "output": 0, "reasoning": 0},
                )
                scope["calls"] += work.attempts
                scope["cost"] += work.attempts * price[2]
                for dimension in tokens:
                    amount = work.attempts * getattr(work, dimension + "_tokens")
                    tokens[dimension] += amount
                    scope[dimension] += amount
            if (
                used_calls + calls > plan.max_calls
                or used_cost + cost > plan.max_cost_microunits
            ):
                raise PaidBudgetError(
                    "BUDGET_EXHAUSTED", "whole workload exceeds remaining budget"
                )
            occupied = {d: 0 for d in tokens}
            scope_occupied: dict[str, dict[str, int]] = {}
            for (
                scope_id,
                held_input,
                held_output,
                held_reasoning,
                usage_json,
                state,
            ) in c.execute(
                "SELECT scope,reserved_input,reserved_output,reserved_reasoning,usage,state FROM reservations WHERE bid=?",
                (bid,),
            ):
                usage = json.loads(usage_json) if usage_json else None
                existing = scope_occupied.setdefault(scope_id, {d: 0 for d in tokens})
                for dimension, held in zip(
                    tokens, (held_input, held_output, held_reasoning)
                ):
                    amount = usage[dimension + "_tokens"] if usage else (held or 0)
                    if state == "anomaly":
                        amount = max(amount, held or 0)
                    occupied[dimension] += amount
                    existing[dimension] += amount
            for dimension, amount in tokens.items():
                if task_totals is not None:
                    occupied[dimension] = task_totals[dimension + "_tokens"]
                if occupied[dimension] + amount > getattr(
                    plan, "max_" + dimension + "_tokens"
                ):
                    raise PaidBudgetError(
                        "BUDGET_EXHAUSTED",
                        "whole workload exceeds remaining token budget",
                    )
            for scope_id, scope in by_scope.items():
                existing = c.execute(
                    "SELECT calls,cost,deadline,stopped FROM scopes WHERE bid=? AND scope=?",
                    (bid, scope_id),
                ).fetchone()
                if existing and (existing[3] or now >= existing[2]):
                    raise PaidBudgetError(
                        "RUN_EXHAUSTED", "workload scope stopped or expired"
                    )
                if scope["calls"] + (existing[0] if existing else 0) > min(
                    plan.max_run_calls, MAX_RUN_CALLS
                ) or scope["cost"] + (existing[1] if existing else 0) > min(
                    plan.max_run_cost_microunits, MAX_RUN_COST_MICROUNITS
                ):
                    raise PaidBudgetError(
                        "RUN_EXHAUSTED", "workload scope exceeds limit"
                    )
                for dimension in tokens:
                    if scope[dimension] + scope_occupied.get(scope_id, {}).get(
                        dimension, 0
                    ) > getattr(plan, "max_run_" + dimension + "_tokens"):
                        raise PaidBudgetError(
                            "RUN_EXHAUSTED", "workload scope token limit"
                        )
            plan_ref = expected_plan_ref
            if requirements:
                serialized = json.dumps(
                    sorted(
                        [work.__dict__ for work in requirements],
                        key=lambda w: (
                            w["scope_id"],
                            w["provider"],
                            w["model"],
                            w["attempts"],
                        ),
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                )
                digest = hashlib.sha256(serialized.encode()).hexdigest()
                proposed = hashlib.sha256((bid + ":" + digest).encode()).hexdigest()
                assigned = {
                    row[0]
                    for scope in by_scope
                    for row in c.execute(
                        "SELECT plan_id FROM workload_plan_scopes WHERE bid=? AND scope=?",
                        (bid, scope),
                    )
                }
                if assigned and assigned != {proposed}:
                    raise PaidBudgetError(
                        "WORKLOAD_PLAN_CONFLICT",
                        "scope already belongs to a frozen workload plan",
                    )
                if expected_plan_ref is not None and expected_plan_ref != proposed:
                    raise PaidBudgetError(
                        "WORKLOAD_PLAN_CONFLICT", "frozen workload changed"
                    )
                existing_plan = c.execute(
                    "SELECT stopped,deadline,calls,max_calls,cost,max_cost FROM workload_plans WHERE id=?",
                    (proposed,),
                ).fetchone()
                if existing_plan and (
                    existing_plan[0]
                    or now >= existing_plan[1]
                    or existing_plan[2] >= existing_plan[3]
                    or existing_plan[4] >= existing_plan[5]
                ):
                    raise PaidBudgetError(
                        "WORKLOAD_PLAN_EXHAUSTED", "workload plan permanently stopped"
                    )
                c.execute(
                    "INSERT INTO workload_plans(id,bid,input_hash,max_calls,max_cost,max_input,max_output,max_reasoning,deadline) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                    (
                        proposed,
                        bid,
                        digest,
                        calls,
                        cost,
                        tokens["input"],
                        tokens["output"],
                        tokens["reasoning"],
                        min(
                            plan.deadline_epoch_ms,
                            now + min(plan.max_run_duration_ms, MAX_RUN_DURATION_MS),
                        ),
                    ),
                )
                for planned_scope_id in by_scope:
                    c.execute(
                        "INSERT INTO workload_plan_scopes(plan_id,bid,scope) VALUES(?,?,?) ON CONFLICT(bid,scope) DO NOTHING",
                        (proposed, bid, planned_scope_id),
                    )
                plan_ref = proposed
            return {
                "maximum_calls": calls,
                "maximum_cost_microunits": cost,
                "ready": True,
                "deadline_epoch_ms": c.execute(
                    "SELECT deadline FROM workload_plans WHERE id=?", (plan_ref,)
                ).fetchone()[0]
                if plan_ref
                else plan.deadline_epoch_ms,
                "budget_ref": bid,
                "plan_ref": plan_ref,
            }

    @_closed
    def check_workload_plan(self, plan_ref: str, scope_id: str) -> None:
        with closing(self._db()) as c:
            row = c.execute(
                "SELECT p.bid,p.deadline,p.calls,p.max_calls,p.cost,p.max_cost,p.stopped,b.stopped FROM workload_plans p JOIN budgets b ON b.id=p.bid WHERE p.id=?",
                (plan_ref,),
            ).fetchone()
            active = c.execute(
                "SELECT id FROM budgets ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if (
                not row
                or not active
                or active[0] != row[0]
                or row[6]
                or row[7]
                or int(time.time() * 1000) >= row[1]
                or row[2] >= row[3]
                or row[4] >= row[5]
            ):
                raise PaidBudgetError(
                    "WORKLOAD_PLAN_EXHAUSTED", "workload plan stopped or exhausted"
                )
            bound = c.execute(
                "SELECT plan_id FROM workload_plan_scopes WHERE bid=? AND scope=?",
                (row[0], scope_id),
            ).fetchone()
            if not bound or bound[0] != plan_ref:
                raise PaidBudgetError(
                    "WORKLOAD_SCOPE_NOT_BOUND", "scope not bound to frozen workload"
                )

    @_closed
    def reserve(
        self,
        budget_id: str | None,
        scope_id: str,
        provider: str,
        model: str,
        request_bytes: int,
        output_tokens: int,
        *,
        input_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        task_binding: TaskPaidBinding | None = None,
    ) -> PaidReservation:
        _pos(request_bytes, "request_bytes", True)
        _pos(output_tokens, "output_tokens", True)
        if input_tokens is None or reasoning_tokens is None:
            raise PaidBudgetError("INVALID_PLAN", "explicit token reservation required")
        _pos(input_tokens, "input_tokens", True)
        _pos(reasoning_tokens, "reasoning_tokens", True)
        if reasoning_tokens > output_tokens:
            raise PaidBudgetError("PAYLOAD_LIMIT", "reasoning exceeds output")
        c = self._db()
        try:
            c.execute("BEGIN IMMEDIATE")
            active = c.execute(
                "SELECT id FROM budgets ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            bid = budget_id or (active[0] if active else None)
            if not bid:
                raise PaidBudgetError("NO_BUDGET", "no active budget")

            row = c.execute(
                "SELECT plan,calls,cost,run_calls,run_cost,inflight,stopped,first_ms FROM budgets WHERE id=?",
                (bid,),
            ).fetchone()
            if not row:
                raise PaidBudgetError("NO_BUDGET", "unknown budget")
            p = PaidBudgetPlan(**json.loads(row[0])).__dict__
            price = c.execute(
                "SELECT req,out,cost,pricing FROM prices WHERE bid=? AND provider=? AND model=?",
                (bid, provider, model),
            ).fetchone()
            if not price:
                raise PaidBudgetError("UNKNOWN_PRICE", "price unavailable")
            if p["max_input_tokens"] <= 0 or not price[3]:
                raise PaidBudgetError(
                    "INVALID_PLAN", "legacy authorization requires replacement"
                )
            frozen = PaidPriceLimit(**json.loads(price[3]))
            worst = max(
                calculate_paid_cost(PaidUsage(input_tokens, output_tokens), frozen),
                calculate_paid_cost(
                    PaidUsage(input_tokens, output_tokens, input_tokens), frozen
                ),
            )
            if worst > price[2]:
                raise PaidBudgetError(
                    "INVALID_PRICE", "attempt cost below reserved worst case"
                )
            if input_tokens > frozen.max_input_tokens:
                raise PaidBudgetError("PAYLOAD_LIMIT", "input exceeds price limit")
            if request_bytes > price[0] or output_tokens > price[1]:
                raise PaidBudgetError("PAYLOAD_LIMIT", "payload exceeds limit")
            now = int(time.time() * 1000)
            sr = c.execute(
                "SELECT calls,cost,deadline,stopped FROM scopes WHERE bid=? AND scope=?",
                (bid, scope_id),
            ).fetchone()
            first = now
            deadline = (
                sr[2]
                if sr
                else min(
                    p["deadline_epoch_ms"],
                    now + min(p["max_run_duration_ms"], MAX_RUN_DURATION_MS),
                )
            )
            if row[6] or now >= deadline or (sr and sr[3]):
                raise PaidBudgetError("BUDGET_STOPPED", "budget stopped or expired")
            if (
                row[1] + 1 > p["max_calls"]
                or row[2] + price[2] > p["max_cost_microunits"]
            ):
                c.execute("UPDATE budgets SET stopped='exhausted' WHERE id=?", (bid,))
                c.commit()
                raise PaidBudgetError("BUDGET_EXHAUSTED", "budget exhausted")
            for dimension, requested in (
                ("input", input_tokens),
                ("output", output_tokens),
                ("reasoning", reasoning_tokens),
            ):
                rows = c.execute(
                    "SELECT scope,reserved_"
                    + dimension
                    + ",usage,state FROM reservations WHERE bid=?",
                    (bid,),
                ).fetchall()
                total = scope_total = 0
                for token_scope, held, usage_json, state in rows:
                    amount = (
                        json.loads(usage_json)[dimension + "_tokens"]
                        if usage_json
                        else (held or 0)
                    )
                    if state == "anomaly":
                        amount = max(amount, held or 0)
                    total += amount
                    if token_scope == scope_id:
                        scope_total += amount
                if total + requested > p["max_" + dimension + "_tokens"]:
                    c.execute(
                        "UPDATE budgets SET stopped='exhausted' WHERE id=?", (bid,)
                    )
                    c.commit()
                    raise PaidBudgetError("BUDGET_EXHAUSTED", "token budget exhausted")
                if scope_total + requested > p["max_run_" + dimension + "_tokens"]:
                    c.execute(
                        "INSERT INTO scopes(bid,scope,deadline,stopped) VALUES (?,?,?,1) ON CONFLICT(bid,scope) DO UPDATE SET stopped=1",
                        (bid, scope_id, deadline),
                    )
                    c.commit()
                    raise PaidBudgetError(
                        "RUN_EXHAUSTED", "scope token budget exhausted"
                    )
            if (sr[0] if sr else 0) + 1 > min(p["max_run_calls"], MAX_RUN_CALLS) or (
                sr[1] if sr else 0
            ) + price[2] > min(p["max_run_cost_microunits"], MAX_RUN_COST_MICROUNITS):
                c.execute(
                    "INSERT INTO scopes(bid,scope,deadline,stopped) VALUES (?,?,?,1) ON CONFLICT(bid,scope) DO UPDATE SET stopped=1",
                    (bid, scope_id, deadline),
                )
                c.commit()
                raise PaidBudgetError("RUN_EXHAUSTED", "scope exhausted")
            if (
                row[1] + 1 > p["max_calls"]
                or row[2] + price[2] > p["max_cost_microunits"]
                or c.execute(
                    "SELECT count(*) FROM reservations WHERE active=1"
                ).fetchone()[0]
                + 1
                > p["max_inflight"]
            ):
                raise PaidBudgetError("BUDGET_EXHAUSTED", "budget exhausted")
            workload = c.execute(
                "SELECT p.id,p.max_calls,p.max_cost,p.max_input,p.max_output,p.max_reasoning,p.deadline,p.calls,p.cost,p.stopped FROM workload_plans p JOIN workload_plan_scopes s ON s.plan_id=p.id WHERE s.bid=? AND s.scope=?",
                (bid, scope_id),
            ).fetchone()
            if workload:
                plan_tokens = {"input": 0, "output": 0, "reasoning": 0}
                for (
                    held_input,
                    held_output,
                    held_reasoning,
                    usage_json,
                    state,
                ) in c.execute(
                    "SELECT r.reserved_input,r.reserved_output,r.reserved_reasoning,r.usage,r.state FROM reservations r JOIN workload_plan_scopes s ON s.bid=r.bid AND s.scope=r.scope WHERE s.plan_id=?",
                    (workload[0],),
                ):
                    usage = json.loads(usage_json) if usage_json else None
                    for dimension, held in zip(
                        plan_tokens, (held_input, held_output, held_reasoning)
                    ):
                        amount = usage[dimension + "_tokens"] if usage else (held or 0)
                        plan_tokens[dimension] += (
                            max(amount, held or 0) if state == "anomaly" else amount
                        )
                workload_requested = {
                    "input": input_tokens,
                    "output": output_tokens,
                    "reasoning": reasoning_tokens,
                }
                if (
                    workload[9]
                    or now >= workload[6]
                    or workload[7] + 1 > workload[1]
                    or workload[8] + price[2] > workload[2]
                    or any(
                        plan_tokens[d] + workload_requested[d] > maximum
                        for d, maximum in zip(plan_tokens, workload[3:6])
                    )
                ):
                    c.execute(
                        "UPDATE workload_plans SET stopped=COALESCE(stopped,'exhausted') WHERE id=?",
                        (workload[0],),
                    )
                    c.commit()
                    raise PaidBudgetError(
                        "WORKLOAD_PLAN_EXHAUSTED", "aggregate workload plan exhausted"
                    )
                deadline = min(deadline, workload[6])
            task_deadline = self._task_reserve(
                c,
                bid,
                task_binding,
                frozen,
                (input_tokens, output_tokens, reasoning_tokens),
                now,
            )
            if task_deadline is not None:
                deadline = min(deadline, task_deadline)
            if workload:
                c.execute(
                    "UPDATE workload_plans SET calls=calls+1,cost=cost+? WHERE id=?",
                    (price[2], workload[0]),
                )
            c.execute(
                "INSERT INTO scopes(bid,scope,calls,cost,deadline) VALUES (?,?,1,?,?) ON CONFLICT(bid,scope) DO UPDATE SET calls=calls+1,cost=cost+excluded.cost",
                (bid, scope_id, price[2], deadline),
            )
            c.execute(
                "UPDATE budgets SET calls=calls+1,cost=cost+?,run_calls=run_calls+1,run_cost=run_cost+?,inflight=inflight+1,first_ms=? WHERE id=?",
                (price[2], price[2], first, bid),
            )
            rid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO reservations(id,bid,scope,deadline,active,status,provider,model,reserved_input,reserved_output,reserved_reasoning,reserved_cost,pricing,state) VALUES (?,?,?,?,1,NULL,?,?,?,?,?,?,?,'active')",
                (
                    rid,
                    bid,
                    scope_id,
                    deadline,
                    provider,
                    model,
                    input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    price[2],
                    price[3],
                ),
            )
            c.commit()
            return PaidReservation(rid, deadline)
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @_closed
    def settle(self, reservation_id: str, usage: PaidUsage) -> None:
        c = self._db()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.row_factory = sqlite3.Row
            r = c.execute(
                "SELECT * FROM reservations WHERE id=?", (reservation_id,)
            ).fetchone()
            if not r:
                raise PaidBudgetError("INVALID_RESERVATION", "unknown reservation")
            encoded = json.dumps(usage.__dict__, sort_keys=True)
            if r["usage"]:
                if json.loads(r["usage"]) == usage.__dict__:
                    return
                raise PaidBudgetError("USAGE_CONFLICT", "conflicting usage report")
            frozen_price = PaidPriceLimit(**json.loads(r["pricing"]))
            numerator = (
                (usage.input_tokens - usage.cached_tokens)
                * frozen_price.input_microunits_per_million
                + usage.cached_tokens * frozen_price.cached_input_microunits_per_million
                + usage.output_tokens * frozen_price.output_microunits_per_million
            )
            cost = (numerator + 999_999) // 1_000_000
            totals = c.execute(
                "SELECT b.cost,b.run_cost,s.cost FROM budgets b JOIN scopes s ON s.bid=b.id WHERE b.id=? AND s.scope=?",
                (r["bid"], r["scope"]),
            ).fetchone()
            delta_upper = max(0, cost - r["reserved_cost"])
            if cost > 2**63 - 1 or (
                totals and any(total + delta_upper > 2**63 - 1 for total in totals)
            ):
                c.execute(
                    "UPDATE reservations SET usage=?,actual_cost_decimal=?,state='anomaly' WHERE id=?",
                    (encoded, str(cost), reservation_id),
                )
                c.execute(
                    "UPDATE budgets SET stopped='usage_overflow' WHERE id=?",
                    (r["bid"],),
                )
                c.commit()
                raise PaidBudgetError(
                    "USAGE_OVERFLOW", "reported cost exceeds accounting range"
                )
            exceeded = (
                usage.input_tokens > r["reserved_input"]
                or usage.output_tokens > r["reserved_output"]
                or usage.reasoning_tokens > r["reserved_reasoning"]
                or cost > r["reserved_cost"]
            )
            if not exceeded:
                live = c.execute(
                    "SELECT b.stopped,s.stopped FROM budgets b JOIN scopes s ON s.bid=b.id WHERE b.id=? AND s.scope=?",
                    (r["bid"], r["scope"]),
                ).fetchone()
                if (
                    not r["active"]
                    or r["status"] != 200
                    or not live
                    or live[0]
                    or live[1]
                    or int(time.time() * 1000) >= r["deadline"]
                ):
                    raise PaidBudgetError(
                        "BUDGET_STOPPED", "usage cannot release reservation"
                    )
            effective_cost = max(cost, r["reserved_cost"]) if exceeded else cost
            delta = effective_cost - r["reserved_cost"]
            c.execute(
                "UPDATE reservations SET usage=?,actual_cost=?,state=? WHERE id=?",
                (encoded, cost, "anomaly" if exceeded else "settled", reservation_id),
            )
            c.execute(
                "UPDATE budgets SET cost=cost+?,run_cost=run_cost+? WHERE id=?",
                (delta, delta, r["bid"]),
            )
            c.execute(
                "UPDATE scopes SET cost=cost+? WHERE bid=? AND scope=?",
                (delta, r["bid"], r["scope"]),
            )
            c.execute(
                "UPDATE workload_plans SET cost=cost+?,stopped=CASE WHEN ? THEN COALESCE(stopped,'usage_exceeded') ELSE stopped END WHERE id IN (SELECT plan_id FROM workload_plan_scopes WHERE bid=? AND scope=?)",
                (delta, exceeded, r["bid"], r["scope"]),
            )
            if exceeded:
                c.execute(
                    "UPDATE budgets SET stopped='usage_exceeded' WHERE id=?",
                    (r["bid"],),
                )
            c.commit()
            if exceeded:
                raise PaidBudgetError(
                    "USAGE_EXCEEDED", "reported usage exceeds reservation"
                )
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    @_closed
    def details(self, budget_id: str | None = None) -> dict[str, object]:
        c = self._db()
        try:
            c.execute("BEGIN")
            active = c.execute(
                "SELECT id FROM budgets ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            bid = budget_id or (active[0] if active else None)
            return self._details(c, bid)
        finally:
            c.close()

    def _details(self, c: sqlite3.Connection, bid: str | None) -> dict[str, Any]:
        columns = {r[1] for r in c.execute("PRAGMA table_info(reservations)")}
        if "state" not in columns:
            return {"budget_id": bid, "attempts": []}
        previous_factory = c.row_factory
        c.row_factory = sqlite3.Row
        attempts = []
        for r in c.execute(
            "SELECT * FROM reservations WHERE bid=? ORDER BY rowid", (bid,)
        ):
            attempts.append(
                {
                    "reservation_id": r["id"],
                    "scope_id": r["scope"],
                    "provider": r["provider"],
                    "model": r["model"],
                    "reserved_tokens": {
                        k + "_tokens": r["reserved_" + k]
                        for k in ("input", "output", "reasoning")
                    },
                    "reserved_cost_microunits": r["reserved_cost"],
                    "reported_usage": json.loads(r["usage"]) if r["usage"] else None,
                    "reported_cost_microunits": int(r["actual_cost_decimal"])
                    if r["actual_cost_decimal"] is not None
                    else r["actual_cost"],
                    "cost_overflow": r["actual_cost_decimal"] is not None,
                    "pricing_version": json.loads(r["pricing"])["pricing_version"]
                    if r["pricing"]
                    else None,
                    "state": r["state"],
                    "status": r["status"],
                    "active": bool(r["active"]),
                }
            )
        c.row_factory = previous_factory
        return {"budget_id": bid, "attempts": attempts}

    def _accounting(self, attempts: list[dict[str, Any]]) -> dict[str, object]:
        actual = {k + "_tokens": 0 for k in ("input", "output", "reasoning")}
        held = dict(actual)
        actual_cost = held_cost = unknown = 0
        for a in attempts:
            usage = a["reported_usage"]
            if usage:
                actual_cost += a["reported_cost_microunits"]
                for k in actual:
                    actual[k] += usage[k]
                    if a["state"] == "anomaly":
                        held[k] += max(0, (a["reserved_tokens"][k] or 0) - usage[k])
                if a["state"] == "anomaly":
                    held_cost += max(
                        0,
                        (a["reserved_cost_microunits"] or 0)
                        - a["reported_cost_microunits"],
                    )
            else:
                held_cost += a["reserved_cost_microunits"] or 0
                for k in held:
                    held[k] += a["reserved_tokens"][k] or 0
                unknown += int(a["state"] in ("unknown", "legacy"))
        return {
            "actual_tokens": actual,
            "held_tokens": held,
            "effective_tokens": {k: actual[k] + held[k] for k in actual},
            "actual_cost_microunits": actual_cost,
            "held_cost_microunits": held_cost,
            "unknown_attempts": unknown,
            "cost_overflow": any(a["cost_overflow"] for a in attempts),
        }

    @_closed
    def finish(self, reservation_id: str) -> None:
        c = self._db()
        c.execute("BEGIN IMMEDIATE")
        changed = c.execute(
            "UPDATE reservations SET active=0,state=CASE WHEN state='active' THEN 'unknown' ELSE state END WHERE id=? AND active=1",
            (reservation_id,),
        ).rowcount
        bid = c.execute(
            "SELECT bid FROM reservations WHERE id=?", (reservation_id,)
        ).fetchone()
        if bid and changed:
            c.execute(
                "UPDATE budgets SET inflight=CASE WHEN inflight>0 THEN inflight-1 ELSE 0 END WHERE id=?",
                (bid[0],),
            )
        c.commit()
        c.close()

    @_closed
    def check_live(self, reservation_id: str) -> None:
        with closing(self._db()) as c:
            r = c.execute(
                "SELECT r.deadline,r.active,b.stopped,s.stopped,r.bid,r.provider,b.plan FROM reservations r JOIN budgets b ON b.id=r.bid JOIN scopes s ON s.bid=r.bid AND s.scope=r.scope WHERE r.id=?",
                (reservation_id,),
            ).fetchone()
            if (
                r
                and c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_authorizations'"
                ).fetchone()
                and c.execute(
                    "SELECT 1 FROM task_authorizations WHERE id=?", (r[4],)
                ).fetchone()
            ):
                if not self.task_authorization_enabled:
                    raise PaidBudgetError(
                        "CONTINUATION_AUTH_UNSUPPORTED", "task authorization disabled"
                    )
                self._task_provider_check(
                    c, {r[5]}, json.loads(r[6])["max_429_responses"]
                )
        if not r or not r[1] or r[2] or r[3] or int(time.time() * 1000) >= r[0]:
            raise PaidBudgetError("BUDGET_STOPPED", "reservation expired")

    @_closed
    def record_status(self, reservation_id: str, status: int) -> None:
        c = self._db()
        c.execute("BEGIN IMMEDIATE")
        r = c.execute(
            "SELECT bid,provider FROM reservations WHERE id=? AND status IS NULL",
            (reservation_id,),
        ).fetchone()
        if r:
            if status == 402:
                c.execute("UPDATE budgets SET stopped='402' WHERE id=?", (r[0],))
            elif status == 429:
                c.execute("UPDATE budgets SET r429=r429+1 WHERE id=?", (r[0],))
                c.execute(
                    "UPDATE budgets SET stopped='429' WHERE id=? AND r429 >= (SELECT json_extract(plan,'$.max_429_responses') FROM budgets WHERE id=?)",
                    (r[0], r[0]),
                )
            c.execute(
                "UPDATE reservations SET status=? WHERE id=?", (status, reservation_id)
            )
            if (
                status in {402, 429}
                and c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_authorizations'"
                ).fetchone()
                and c.execute(
                    "SELECT 1 FROM task_authorizations WHERE id=?", (r[0],)
                ).fetchone()
            ):
                threshold = c.execute(
                    "SELECT MIN(json_extract(b.plan,'$.max_429_responses')) FROM budgets b JOIN prices p ON p.bid=b.id WHERE p.provider=?",
                    (r[1],),
                ).fetchone()[0]
                cumulative = c.execute(
                    "SELECT COUNT(*) FROM reservations WHERE provider=? AND status=429",
                    (r[1],),
                ).fetchone()[0]
                if status == 402 or cumulative >= threshold:
                    c.execute(
                        "UPDATE budgets SET stopped=COALESCE(stopped,?) WHERE id IN (SELECT bid FROM prices WHERE provider=?)",
                        (str(status), r[1]),
                    )
        c.commit()
        c.close()

    @_closed
    def stop(self, budget_id: str, reason: str) -> None:
        c = self._db()
        c.execute(
            "UPDATE budgets SET stopped=? WHERE id=?", ("operator_stop", budget_id)
        )
        c.commit()
        c.close()

    @_closed
    def snapshot(self, budget_id: str | None = None) -> dict[str, object]:
        c = self._db()
        try:
            c.execute("BEGIN")
            active = c.execute(
                "SELECT id FROM budgets ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            bid = budget_id or (active[0] if active else None)
            r = c.execute(
                "SELECT id,calls,cost,run_calls,run_cost,inflight,stopped,r429,plan FROM budgets WHERE id=?",
                (bid,),
            ).fetchone()
            if not r:
                return {}
            plan = PaidBudgetPlan(**json.loads(r[8]))
            result = dict(
                zip(
                    (
                        "budget_id",
                        "calls",
                        "cost_microunits",
                        "run_calls",
                        "run_cost_microunits",
                        "inflight",
                        "stopped",
                        "429_responses",
                    ),
                    r[:8],
                )
            )
            result.update(
                {
                    "limits": dict(plan.__dict__),
                    "remaining_calls": max(0, plan.max_calls - r[1]),
                    "remaining_cost_microunits": max(
                        0, plan.max_cost_microunits - r[2]
                    ),
                    "deadline_epoch_ms": plan.deadline_epoch_ms,
                    "prices": [
                        dict(
                            zip(
                                (
                                    "provider",
                                    "model",
                                    "max_request_bytes",
                                    "max_output_tokens",
                                    "max_cost_microunits_per_attempt",
                                    "pricing_source",
                                ),
                                row,
                            )
                        )
                        for row in c.execute(
                            "SELECT provider,model,req,out,cost,src FROM prices WHERE bid=? ORDER BY provider,model",
                            (bid,),
                        )
                    ],
                }
            )
            price_columns = {
                column[1] for column in c.execute("PRAGMA table_info(prices)")
            }
            if "pricing" in price_columns:
                frozen_prices = {
                    (row[0], row[1]): json.loads(row[2])
                    for row in c.execute(
                        "SELECT provider,model,pricing FROM prices WHERE bid=? AND pricing IS NOT NULL",
                        (bid,),
                    )
                }
                for public_price in result["prices"]:
                    public_price.update(
                        frozen_prices.get(
                            (public_price["provider"], public_price["model"]), {}
                        )
                    )
            attempts = self._details(c, bid)["attempts"]
            result["accounting"] = self._accounting(attempts)
            result["accounting"]["held_cost_microunits"] = max(
                result["accounting"]["held_cost_microunits"],
                r[2] - result["accounting"]["actual_cost_microunits"],
            )
            if result["accounting"]["cost_overflow"]:
                result["remaining_cost_microunits"] = 0
            result["scopes"] = [
                {
                    "scope_id": scope[0],
                    "calls": scope[1],
                    "cost_microunits": scope[2],
                    "stopped": scope[3],
                    "accounting": self._accounting(
                        [a for a in attempts if a["scope_id"] == scope[0]]
                    ),
                }
                for scope in c.execute(
                    "SELECT scope,calls,cost,stopped FROM scopes WHERE bid=? ORDER BY scope",
                    (bid,),
                )
            ]
            for scope_result in result["scopes"]:
                scope_result["accounting"]["held_cost_microunits"] = max(
                    scope_result["accounting"]["held_cost_microunits"],
                    scope_result["cost_microunits"]
                    - scope_result["accounting"]["actual_cost_microunits"],
                )
            return result
        finally:
            c.close()
