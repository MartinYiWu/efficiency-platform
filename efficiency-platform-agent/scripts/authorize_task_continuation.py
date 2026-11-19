"""仅本机显式授权；默认只读预览，不读取业务HTTP参数或供应商凭据。"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from efficiency_platform_agent.configuration.paid_budget import default_paid_budget_path
from efficiency_platform_agent.configuration.task_authorization import (
    task_authorization_enabled,
)
from efficiency_platform_agent.core.paid_budget import PaidBudgetError, PaidPriceLimit
from efficiency_platform_agent.core.task_authorization import TaskContinuation
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def main(argv: Sequence[str] | None = None, *, ledger_path: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="预览或显式创建同task有限后继授权")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--continuation-of", required=True)
    parser.add_argument("--max-total-cost-cny", required=True)
    parser.add_argument("--max-total-http", required=True, type=int)
    parser.add_argument("--max-input-tokens", required=True, type=int)
    parser.add_argument("--max-output-tokens", required=True, type=int)
    parser.add_argument("--max-reasoning-tokens", required=True, type=int)
    parser.add_argument(
        "--expires-at", required=True, help="带时区ISO8601绝对截止，最长10分钟"
    )
    parser.add_argument("--price-limit-file", required=True, type=Path)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        amount = Decimal(args.max_total_cost_cny) * 1_000_000
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError
        expiry = datetime.fromisoformat(args.expires_at)
        if expiry.tzinfo is None:
            raise ValueError
        encoded = json.loads(args.price_limit_file.read_text(encoding="utf-8"))
        if not isinstance(encoded, list):
            raise TypeError
        prices = tuple(PaidPriceLimit(**item) for item in encoded)
        request = TaskContinuation(
            args.task_id,
            args.continuation_of,
            int(amount),
            args.max_total_http,
            args.max_input_tokens,
            args.max_output_tokens,
            args.max_reasoning_tokens,
            int(expiry.timestamp() * 1000),
        )
        path = ledger_path or default_paid_budget_path()
        if str(path.resolve()).startswith("\\\\"):
            raise PaidBudgetError(
                "TASK_LEDGER_LOCAL_REQUIRED", "local user ledger required"
            )
        ledger = SqlitePaidBudgetLedger(
            path,
            read_only=True,
            task_authorization_enabled=task_authorization_enabled(),
        )
        if args.confirm:
            ledger.read_only = False
        result = ledger.authorize_task_continuation(
            request, prices, confirm=args.confirm
        )
        print(
            json.dumps(
                {"mode": "confirmed" if args.confirm else "preview", **result},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except PaidBudgetError as error:
        print(json.dumps({"code": error.code}, ensure_ascii=False))
    except (OSError, ValueError, TypeError, OverflowError, InvalidOperation):
        print(json.dumps({"code": "INVALID_LOCAL_AUTHORIZATION_INPUT"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
