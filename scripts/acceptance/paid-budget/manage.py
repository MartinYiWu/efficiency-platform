"""仅管理本机付费总账，不加载密钥或调用网络。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import fields
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "efficiency-platform-agent" / "src")
)

from efficiency_platform_agent.configuration.paid_budget import default_paid_budget_path
from efficiency_platform_agent.core.paid_budget import (
    PaidBudgetError,
    PaidBudgetPlan,
    PaidPriceLimit,
)
from efficiency_platform_agent.persistence.paid_budget import SqlitePaidBudgetLedger


def load_plan(path: Path) -> tuple[PaidBudgetPlan, tuple[PaidPriceLimit, ...]]:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    data = json.loads(
        path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object
    )
    if not isinstance(data, dict) or set(data) != {
        "budget",
        "prices",
        "pricing_verified",
    }:
        raise ValueError("invalid plan fields")
    if data["pricing_verified"] is not True:
        raise ValueError("pricing must be verified")
    budget = data["budget"]
    if not isinstance(budget, dict) or set(budget) != {
        f.name for f in fields(PaidBudgetPlan)
    }:
        raise ValueError("invalid budget fields")
    if not isinstance(budget["budget_id"], str) or not budget["budget_id"].strip():
        raise ValueError("budget id required")
    for name, value in budget.items():
        if name != "budget_id" and (
            type(value) is not int
            or value < (0 if name in {"max_output_tokens", "max_reasoning_tokens", "max_run_output_tokens", "max_run_reasoning_tokens"} else 1)
            or value > 2**63 - 1
        ):
            raise ValueError("budget limits must be positive integers")
    if (budget["max_reasoning_tokens"] > budget["max_output_tokens"]
        or budget["max_run_reasoning_tokens"] > budget["max_run_output_tokens"]):
        raise ValueError("reasoning exceeds output budget")
    if budget["deadline_epoch_ms"] <= int(time.time() * 1000):
        raise ValueError("deadline must be in the future")
    prices = data["prices"]
    if not isinstance(prices, list) or not prices:
        raise ValueError("verified prices required")
    parsed = []
    identities = set()
    for price in prices:
        if not isinstance(price, dict) or set(price) != {
            f.name for f in fields(PaidPriceLimit)
        }:
            raise ValueError("invalid price fields")
        for name in ("provider", "model", "pricing_source", "pricing_version"):
            if not isinstance(price[name], str) or not price[name].strip():
                raise ValueError("price identity required")
        for name in (
            "max_request_bytes",
            "max_output_tokens",
            "max_cost_microunits_per_attempt",
            "max_input_tokens",
            "input_microunits_per_million",
            "cached_input_microunits_per_million",
            "output_microunits_per_million",
        ):
            value = price[name]
            if type(value) is not int or value < (
                0 if name in {"max_output_tokens", "cached_input_microunits_per_million", "output_microunits_per_million"} else 1
            ) or value > 2**63 - 1:
                raise ValueError("invalid price limit")
        if price["provider"] == "deepseek" and price["output_microunits_per_million"] == 0:
            raise ValueError("generation output rate required")
        identity = (price["provider"], price["model"])
        if identity in identities:
            raise ValueError("duplicate price identity")
        identities.add(identity)
        parsed.append(PaidPriceLimit(**price))
    return PaidBudgetPlan(**budget), tuple(parsed)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=default_paid_budget_path())
    commands = parser.add_subparsers(dest="command", required=True)
    authorize = commands.add_parser("authorize")
    authorize.add_argument("--plan", type=Path, required=True)
    authorize.add_argument("--confirm-write", action="store_true")
    commands.add_parser("status")
    details = commands.add_parser("details")
    details.add_argument("--budget-id")
    stop = commands.add_parser("stop")
    stop.add_argument("--budget-id", required=True)
    stop.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("authorize", "stop") and not args.confirm_write:
            raise ValueError("--confirm-write required")
        if args.command == "authorize":
            plan, prices = load_plan(args.plan)
            ledger = SqlitePaidBudgetLedger(args.ledger)
            ledger.authorize(plan, prices)
            result = ledger.snapshot(plan.budget_id)
        elif args.command == "stop":
            if not args.ledger.exists():
                raise ValueError("ledger does not exist")
            ledger = SqlitePaidBudgetLedger(args.ledger)
            ledger.stop(args.budget_id, "operator_stop")
            result = ledger.snapshot(args.budget_id)
        elif not args.ledger.exists():
            result = {"active_budget_id": None}
        elif args.command == "details":
            result = SqlitePaidBudgetLedger(args.ledger, read_only=True).details(args.budget_id)
        else:
            result = SqlitePaidBudgetLedger(args.ledger, read_only=True).snapshot()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except PaidBudgetError as exc:
        print(
            json.dumps(
                {"error": exc.code, "message": exc.safe_message}, ensure_ascii=False
            )
        )
    except (ValueError, TypeError, OSError):
        print(
            json.dumps(
                {
                    "error": "INVALID_INPUT",
                    "message": "输入或本地账本不可用；未显示原始内容。",
                },
                ensure_ascii=False,
            )
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
