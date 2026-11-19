"""原SQLite本机schema管理；预检默认只读，--confirm才备份及迁移。"""

import argparse
import json
import sqlite3
from pathlib import Path

from efficiency_platform_agent.configuration.paid_budget import default_paid_budget_path
from efficiency_platform_agent.core.paid_budget import PaidBudgetError
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def main() -> int:
    parser = argparse.ArgumentParser(description="D24本机总账schema预检/备份/迁移/核验")
    parser.add_argument("--backup-path", type=Path, required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        path = default_paid_budget_path().resolve()
        if str(path).startswith("\\\\"):
            raise PaidBudgetError("TASK_LEDGER_LOCAL_REQUIRED", "local ledger required")
        ledger = SqlitePaidBudgetLedger(path, read_only=True)
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise PaidBudgetError("LEDGER_UNAVAILABLE", "integrity check failed")
            before = connection.execute(
                "SELECT COUNT(*),COALESCE(SUM(calls),0),COALESCE(SUM(cost),0),COALESCE(SUM(inflight),0) FROM budgets"
            ).fetchone()
        if args.confirm:
            # 禁止构造器在备份前做任何旧schema迁移。
            ledger.read_only = False
            ledger.initialize_task_authorization_schema(args.backup_path)
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                after = connection.execute(
                    "SELECT COUNT(*),COALESCE(SUM(calls),0),COALESCE(SUM(cost),0),COALESCE(SUM(inflight),0) FROM budgets"
                ).fetchone()
            if before != after:
                raise PaidBudgetError(
                    "TASK_SCHEMA_VERIFY_FAILED", "accounting changed during migration"
                )
        print(
            json.dumps(
                {
                    "mode": "migrated" if args.confirm else "preview",
                    "accounting": before,
                    "schema_version": 1,
                    "default_enabled": False,
                }
            )
        )
        return 0
    except PaidBudgetError as error:
        print(json.dumps({"code": error.code}))
    except (sqlite3.Error, OSError):
        print(json.dumps({"code": "LEDGER_UNAVAILABLE"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
