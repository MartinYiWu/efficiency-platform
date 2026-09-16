from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
    operation_specialist_capability_ids,
)


class SpecialistContractTests(unittest.TestCase):
    def test_capability_catalog_is_unique_and_complete(self):
        values = operation_specialist_capability_ids()
        self.assertEqual(len(values), 11)
        self.assertEqual(len(set(values)), 11)
        self.assertEqual(
            values[0], OperationSpecialistCapabilityId.RESEARCH_INSIGHT.value
        )


if __name__ == "__main__":
    unittest.main()
