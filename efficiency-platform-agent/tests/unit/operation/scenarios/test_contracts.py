from __future__ import annotations

import unittest
from dataclasses import fields

from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioSubmission,
)


class ScenarioContractTests(unittest.TestCase):
    def test_submission_has_only_inbound_fields(self):
        names = {item.name for item in fields(ScenarioSubmission)}
        self.assertEqual(
            names,
            {
                "contract_version",
                "submission_id",
                "scenario_id",
                "manifest_semantic_version",
                "plan_id",
                "request",
                "task_spec",
                "profile_candidates",
                "evidence_pack",
            },
        )
        self.assertNotIn("operation_plan", names)


if __name__ == "__main__":
    unittest.main()
