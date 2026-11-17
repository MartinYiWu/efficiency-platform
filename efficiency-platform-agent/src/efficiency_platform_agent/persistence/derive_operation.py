"""复用已存在付费总账连接的独立 derive 技术租约。"""

import json
import time
import uuid
from contextlib import closing
from dataclasses import asdict

from efficiency_platform_agent.core.derive_ports import DeriveLease, DeriveOperation
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import (
    SqlitePaidBudgetLedger,
    _closed,
)


class SqliteDeriveOperationStore:
    def __init__(self, ledger: SqlitePaidBudgetLedger):
        if type(ledger) is not SqlitePaidBudgetLedger or ledger.read_only:
            raise ValueError("DERIVE_EXISTING_LEDGER_REQUIRED")
        self.ledger = ledger

    @_closed
    def initialize(self) -> None:
        """由本机迁移边界显式调用；构造或业务请求绝不隐式建表。"""
        with closing(self.ledger._db()) as db, db:
            db.execute("SELECT tenant,run FROM execution_runs LIMIT 0")
            db.execute(
                "CREATE TABLE IF NOT EXISTS derive_operations (tenant TEXT NOT NULL,task TEXT NOT NULL,"
                "binding TEXT NOT NULL,fingerprint TEXT NOT NULL,token TEXT NOT NULL,"
                "state TEXT NOT NULL,result BLOB,PRIMARY KEY(tenant,task))"
            )

    @staticmethod
    def _binding(operation: DeriveOperation) -> str:
        return json.dumps(
            asdict(operation), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    @staticmethod
    def _key(operation: DeriveOperation) -> tuple[str, str]:
        return operation.scope.conversation.tenant_id, operation.scope.task_id

    def _check_run(self, db, operation: DeriveOperation) -> None:
        tenant, _ = self._key(operation)
        row = db.execute(
            "SELECT deadline,stopped,context_identity FROM execution_runs WHERE tenant=? AND run=?",
            (tenant, operation.run_id),
        ).fetchone()
        identity = json.dumps(
            asdict(operation.scope.conversation),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if (
            row is None
            or row[1]
            or row[2] != identity
            or time.time() >= operation.deadline_epoch_seconds
            or operation.deadline_epoch_seconds * 1000 > row[0]
        ):
            raise PaidBudgetError(
                "DERIVE_ORIGINAL_EXECUTION_REQUIRED",
                "derive original execution unavailable",
            )

    @_closed
    def claim(self, operation: DeriveOperation, fingerprint: str) -> DeriveLease:
        if (
            not isinstance(operation, DeriveOperation)
            or not fingerprint
            or len(fingerprint) > 128
        ):
            raise PaidBudgetError("DERIVE_BINDING_INVALID", "derive binding invalid")
        with closing(self.ledger._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._check_run(db, operation)
            key = self._key(operation)
            row = db.execute(
                "SELECT binding,fingerprint,token,state,result FROM derive_operations WHERE tenant=? AND task=?",
                key,
            ).fetchone()
            if row is not None:
                if row[0] != self._binding(operation) or row[1] != fingerprint:
                    raise PaidBudgetError(
                        "DERIVE_BINDING_CONFLICT", "derive opportunity binding changed"
                    )
                if row[3] == "SUCCEEDED" and row[4] is not None:
                    return DeriveLease(operation, fingerprint, row[2], row[4])
                raise PaidBudgetError(
                    "DERIVE_OPPORTUNITY_BLOCKED", "derive opportunity already reserved"
                )
            previous = db.execute(
                "SELECT input_hash FROM execution_operations WHERE tenant=? AND run=? AND operation=?",
                (key[0], operation.run_id, operation.operation_id),
            ).fetchone()
            if previous is not None:
                raise PaidBudgetError(
                    "DERIVE_OPERATION_ALREADY_USED", "derive operation already used"
                )
            token = uuid.uuid4().hex
            db.execute(
                "INSERT INTO derive_operations VALUES (?,?,?,?,?,'LEASED',NULL)",
                (*key, self._binding(operation), fingerprint, token),
            )
            db.execute(
                "INSERT INTO execution_operations(tenant,run,operation,input_hash) VALUES(?,?,?,?)",
                (key[0], operation.run_id, operation.operation_id, fingerprint),
            )
            return DeriveLease(operation, fingerprint, token)

    def _check_lease(self, db, lease: DeriveLease) -> None:
        self._check_run(db, lease.operation)
        row = db.execute(
            "SELECT binding,fingerprint,token,state FROM derive_operations WHERE tenant=? AND task=?",
            self._key(lease.operation),
        ).fetchone()
        if row != (
            self._binding(lease.operation),
            lease.fingerprint,
            lease.token,
            "LEASED",
        ):
            raise PaidBudgetError(
                "DERIVE_LEASE_BLOCKED", "derive opportunity unavailable"
            )

    @_closed
    def check_live(self, lease: DeriveLease) -> None:
        with closing(self.ledger._db()) as db:
            self._check_lease(db, lease)

    def consume_attempt(self, lease: DeriveLease) -> None:
        self.check_live(lease)
        self.ledger.consume_execution_attempt(
            self._key(lease.operation)[0],
            lease.operation.run_id,
            lease.operation.operation_id,
        )

    @_closed
    def succeed(self, lease: DeriveLease, sealed_result: bytes) -> None:
        if type(sealed_result) is not bytes or not 0 < len(sealed_result) <= 1_000_000:
            raise ValueError("DERIVE_SEALED_RESULT_INVALID")
        with closing(self.ledger._db()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._check_lease(db, lease)
            db.execute(
                "UPDATE derive_operations SET state='SUCCEEDED',result=? WHERE tenant=? AND task=?",
                (sealed_result, *self._key(lease.operation)),
            )

    @_closed
    def fail(self, lease: DeriveLease) -> None:
        with closing(self.ledger._db()) as db, db:
            db.execute(
                "UPDATE derive_operations SET state='UNKNOWN' WHERE tenant=? AND task=? AND token=? AND state='LEASED'",
                (*self._key(lease.operation), lease.token),
            )
