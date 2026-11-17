import importlib.util
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

import test_manage

spec = importlib.util.spec_from_file_location("readiness", Path(__file__).with_name("readiness.py"))
readiness = importlib.util.module_from_spec(spec)
if spec.loader and Path(spec.origin).exists():
    spec.loader.exec_module(readiness)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        fixture = test_manage.ManageTests()
        fixture.setUp()
        self.addCleanup(fixture.tmp.cleanup)
        self.plan = fixture.plan
        self.data = fixture.data
        self.data["budget"].update(max_input_tokens=200, max_run_input_tokens=200)
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        self.cases = fixture.root / "cases.json"
        self.items = [{"key": "general", "question": "private question", "category": "通用", "description": "general path", "expected_max_attempts": 1}]
        self.cases.write_text(json.dumps(self.items), encoding="utf-8")

    def report(self, confirmed=False):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), patch.object(readiness.manage, "SqlitePaidBudgetLedger", side_effect=AssertionError("ledger forbidden")):
            return readiness.build_report(self.plan, self.cases, confirmed)

    def test_api_exists(self):
        self.assertTrue(hasattr(readiness, "build_report"))

    def test_confirmation_is_required_and_no_question_in_report(self):
        result = self.report()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("ACCOUNT_LIMIT_NOT_CONFIRMED", result["blockers"])
        self.assertNotIn("private question", json.dumps(result))
        self.assertEqual(self.report(True)["status"], "READY_FOR_REVIEW")

    def test_invalid_budget_and_price_block_without_state(self):
        for mutate in (lambda d: d["budget"].update(max_calls=0), lambda d: d.update(pricing_verified=False), lambda d: d["budget"].update(max_run_calls=True)):
            original = json.loads(json.dumps(self.data))
            mutate(self.data)
            self.plan.write_text(json.dumps(self.data), encoding="utf-8")
            self.assertIn("INVALID_PLAN", self.report()["blockers"])
            self.data = original

    def test_cases_are_unique_small_and_bounded(self):
        for items in ([], self.items * 2, [dict(self.items[0], key=str(i), question=str(i)) for i in range(4)], [dict(self.items[0], expected_max_attempts=True)], [dict(self.items[0], expected_max_attempts=3)]):
            self.cases.write_text(json.dumps(items), encoding="utf-8")
            self.assertEqual(self.report(True)["status"], "BLOCKED")

    def test_report_refuses_overwrite(self):
        out = self.cases.parent / "report.json"
        readiness.write_report(out, self.report())
        with self.assertRaises(FileExistsError):
            readiness.write_report(out, self.report())

    def test_declared_attempts_must_fit_token_limits(self):
        self.data["budget"]["max_run_input_tokens"] = 99
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertIn("ATTEMPT_TOKENS_EXCEED_BUDGET", self.report(True)["blockers"])

    def test_reasoning_zero_cannot_cover_unknown_deepseek_reasoning(self):
        self.data["prices"][0]["provider"] = "deepseek"
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertIn("ATTEMPT_TOKENS_EXCEED_BUDGET", self.report(True)["blockers"])

    def test_price_worst_cost_and_core_validation_are_blocked(self):
        self.data["prices"][0]["max_cost_microunits_per_attempt"] = 1
        self.data["prices"][0]["input_microunits_per_million"] = 1000000
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertIn("INVALID_PLAN", self.report(True)["blockers"])
        self.data["budget"]["budget_id"] = "x" * 257
        self.plan.write_text(json.dumps(self.data), encoding="utf-8")
        self.assertIn("INVALID_PLAN", self.report(True)["blockers"])

    def test_case_identifiers_and_attempts_are_bounded(self):
        for changes in ({"key": "x" * 257}, {"expected_max_attempts": 2**63}):
            self.cases.write_text(json.dumps([dict(self.items[0], **changes)]), encoding="utf-8")
            self.assertIn("INVALID_CASES", self.report(True)["blockers"])


if __name__ == "__main__":
    unittest.main()
