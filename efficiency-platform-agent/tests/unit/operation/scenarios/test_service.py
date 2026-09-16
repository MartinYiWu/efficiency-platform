from __future__ import annotations

import inspect
import unittest

from efficiency_platform_agent.agents.operation.scenarios.service import (
    ScenarioPackService,
)


class ScenarioPackServiceTests(unittest.TestCase):
    def test_run_has_single_submission_argument(self):
        parameters = tuple(inspect.signature(ScenarioPackService.run).parameters)
        self.assertEqual(parameters, ("self", "submission"))

    def test_sample_or_unknown_object_is_rejected_before_side_effects(self):
        service = ScenarioPackService(None, None)
        with self.assertRaises(TypeError):
            import asyncio

            asyncio.run(service.run(object()))


if __name__ == "__main__":
    unittest.main()
