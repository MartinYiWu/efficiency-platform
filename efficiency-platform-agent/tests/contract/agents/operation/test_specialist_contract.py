from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.specialists.contracts import (
    SpecialistExecutionResult,
)
from efficiency_platform_agent.core.multi_agent import BudgetUsage


class SpecialistResultContractTests(unittest.TestCase):
    def test_success_requires_structured_scope_or_artifact(self):
        with self.assertRaises(ValueError):
            SpecialistExecutionResult(
                "operation-specialist-result/1",
                "task-1",
                (),
                (),
                None,
                None,
                None,
                (),
                (),
                None,
                None,
                None,
                BudgetUsage(),
            )


if __name__ == "__main__":
    unittest.main()
