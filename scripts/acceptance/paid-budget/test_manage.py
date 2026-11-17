import contextlib
import hashlib
import importlib.util
import io
import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "paid_manage", Path(__file__).with_name("manage.py")
)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "ledger.sqlite3"
        self.plan = self.root / "plan.json"
        self.data = {
            "budget": {
                "budget_id": "local-test",
                "max_calls": 2,
                "max_cost_microunits": 20,
                "deadline_epoch_ms": int(time.time() * 1000) + 60000,
                "max_run_calls": 2,
                "max_run_cost_microunits": 20,
                "max_run_duration_ms": 10000,
                "max_inflight": 1,
                "max_429_responses": 1,
                "max_input_tokens": 100,
                "max_output_tokens": 20,
                "max_reasoning_tokens": 0,
                "max_run_input_tokens": 100,
                "max_run_output_tokens": 20,
                "max_run_reasoning_tokens": 0,
            },
            "prices": [
                {
                    "provider": "fake",
                    "model": "fake",
                    "max_request_bytes": 100,
                    "max_output_tokens": 10,
                    "max_cost_microunits_per_attempt": 10,
                    "pricing_source": "offline-test-only",
                    "pricing_version": "synthetic-v1",
                    "max_input_tokens": 100,
                    "input_microunits_per_million": 1000,
                    "cached_input_microunits_per_million": 0,
                    "output_microunits_per_million": 1000,
                }
            ],
            "pricing_verified": True,
        }

    def run_cli(self, *args):
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        output = io.StringIO()
        with (
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("network forbidden"),
            ),
            contextlib.redirect_stdout(output),
        ):
            code = manage.main(["--ledger", str(self.ledger), *args])
        return code, json.loads(output.getvalue())

    def test_confirmation_and_preflight_do_not_create_ledger(self):
        self.assertNotEqual(self.run_cli("authorize", "--plan", str(self.plan))[0], 0)
        self.assertFalse(self.ledger.exists())
        for mutation in (
            lambda d: d.update(pricing_verified=False),
            lambda d: d.update(prices=[]),
            lambda d: d["budget"].update(max_calls=0),
            lambda d: d["budget"].update(max_calls=True),
            lambda d: d["budget"].update(extra=1),
            lambda d: d.update(extra=1),
        ):
            original = json.loads(json.dumps(self.data))
            mutation(self.data)
            self.assertNotEqual(
                self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[
                    0
                ],
                0,
            )
            self.assertFalse(self.ledger.exists())
            self.data = original

    def test_token_and_price_preflight_before_opening_ledger(self):
        mutations = [
            lambda d: d["budget"].pop("max_input_tokens"),
            lambda d: d["budget"].update(max_input_tokens=0),
            lambda d: d["budget"].update(max_run_input_tokens=0),
            lambda d: d["budget"].update(max_output_tokens=True),
            lambda d: d["budget"].update(max_reasoning_tokens=21),
            lambda d: d["budget"].update(max_calls=2**63),
            lambda d: d["prices"][0].pop("pricing_version"),
            lambda d: d["prices"][0].update(pricing_version=" "),
            lambda d: d["prices"][0].update(input_microunits_per_million=0),
            lambda d: d["prices"][0].update(cached_input_microunits_per_million=-1),
            lambda d: d["prices"][0].update(output_microunits_per_million=True),
            lambda d: d["prices"][0].update(max_input_tokens=2**63),
            lambda d: d["prices"][0].update(provider="deepseek", output_microunits_per_million=0),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                original = json.loads(json.dumps(self.data))
                mutation(self.data)
                with patch.object(manage, "SqlitePaidBudgetLedger") as ledger:
                    self.assertNotEqual(self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[0], 0)
                    ledger.assert_not_called()
                self.assertFalse(self.ledger.exists())
                self.data = original

    def test_zero_output_and_reasoning_mean_disabled_but_are_valid(self):
        self.data["budget"].update(max_output_tokens=0, max_run_output_tokens=0)
        self.data["prices"][0].update(provider="embedding", max_output_tokens=0, output_microunits_per_million=0)
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        plan, prices = manage.load_plan(self.plan)
        self.assertEqual(plan.max_reasoning_tokens, 0)
        self.assertEqual(prices[0].max_output_tokens, 0)
        self.assertFalse(self.ledger.exists())

    def test_documented_synthetic_cost_does_not_add_reasoning_twice(self):
        from efficiency_platform_agent.core.paid_budget import PaidUsage, calculate_paid_cost
        price = dict(self.data["prices"][0])
        price.update(input_microunits_per_million=1000000, cached_input_microunits_per_million=500000, output_microunits_per_million=2000000)
        self.assertEqual(calculate_paid_cost(PaidUsage(100, 10, cached_tokens=20, reasoning_tokens=4), manage.PaidPriceLimit(**price)), 110)

    def test_details_without_ledger_does_not_create_file(self):
        self.assertEqual(self.run_cli("details", "--budget-id", "missing"), (0, {"active_budget_id": None}))
        self.assertFalse(self.ledger.exists())

    def test_details_is_read_only_and_keeps_unknown_cost(self):
        self.assertEqual(self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[0], 0)
        ledger = manage.SqlitePaidBudgetLedger(self.ledger)
        reservation = ledger.reserve("local-test", "question-1", "fake", "fake", 10, 1, input_tokens=10, reasoning_tokens=0)
        ledger.finish(reservation.reservation_id)
        before = hashlib.sha256(self.ledger.read_bytes()).hexdigest()
        constructor = manage.SqlitePaidBudgetLedger
        with patch.object(manage, "SqlitePaidBudgetLedger", wraps=constructor) as readonly:
            code, result = self.run_cli("details", "--budget-id", "local-test")
            self.assertEqual(code, 0)
            readonly.assert_called_once_with(self.ledger, read_only=True)
        self.assertEqual(hashlib.sha256(self.ledger.read_bytes()).hexdigest(), before)
        self.assertIn("synthetic-v1", json.dumps(result))
        self.assertIn("unknown", json.dumps(result))
        attempt = result["attempts"][0]
        self.assertEqual(attempt["reserved_cost_microunits"], 10)
        self.assertIsNone(attempt["reported_usage"])
        self.assertIsNone(attempt["reported_cost_microunits"])
        self.assertEqual(self.run_cli("status")[1]["cost_microunits"], 10)

    def test_status_without_ledger_is_read_only(self):
        self.assertEqual(self.run_cli("status"), (0, {"active_budget_id": None}))
        self.assertFalse(self.ledger.exists())

    def test_duplicate_and_stop_are_persistent(self):
        self.assertEqual(
            self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[0], 0
        )
        ledger = manage.SqlitePaidBudgetLedger(self.ledger)
        reservation = ledger.reserve("local-test", "scope", "fake", "fake", 10, 1, input_tokens=10, reasoning_tokens=0)
        ledger.finish(reservation.reservation_id)
        before = self.run_cli("status")[1]
        self.assertEqual(before["calls"], 1)
        self.assertEqual(before["cost_microunits"], 10)
        digest = hashlib.sha256(self.ledger.read_bytes()).hexdigest()
        self.assertEqual(self.run_cli("status")[1], before)
        self.assertEqual(hashlib.sha256(self.ledger.read_bytes()).hexdigest(), digest)
        self.assertNotEqual(
            self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[0], 0
        )
        self.assertEqual(self.run_cli("status")[1], before)
        self.assertNotEqual(self.run_cli("stop", "--budget-id", "local-test")[0], 0)
        self.assertEqual(
            self.run_cli("stop", "--budget-id", "local-test", "--confirm-write")[0], 0
        )
        stopped = self.run_cli("status")[1]
        self.assertEqual(self.run_cli("status")[1], stopped)
        self.assertNotEqual(stopped, before)

    def test_status_opens_existing_ledger_read_only(self):
        self.assertEqual(
            self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[0], 0
        )
        constructor = manage.SqlitePaidBudgetLedger
        with patch.object(
            manage, "SqlitePaidBudgetLedger", wraps=constructor
        ) as ledger:
            self.assertEqual(self.run_cli("status")[0], 0)
            ledger.assert_called_once_with(self.ledger, read_only=True)

    def test_invalid_prices_and_duplicate_json_fail_before_ledger(self):
        for name, value in (
            ("max_request_bytes", True),
            ("max_output_tokens", "10"),
            ("max_cost_microunits_per_attempt", 0),
            ("pricing_source", []),
            ("extra", 1),
        ):
            original = json.loads(json.dumps(self.data))
            self.data["prices"][0][name] = value
            self.assertNotEqual(
                self.run_cli("authorize", "--plan", str(self.plan), "--confirm-write")[
                    0
                ],
                0,
            )
            self.assertFalse(self.ledger.exists())
            self.data = original
        self.plan.write_text('{"budget": {}, "budget": {}}', encoding="utf-8")
        with self.assertRaises(ValueError):
            manage.load_plan(self.plan)
        self.assertFalse(self.ledger.exists())


if __name__ == "__main__":
    unittest.main()
