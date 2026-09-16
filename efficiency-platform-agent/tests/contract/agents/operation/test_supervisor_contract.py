from __future__ import annotations

import unittest

from efficiency_platform_agent.contracts.supervisor_events import (
    SupervisorEventType,
    SupervisorEventV1,
)


class SupervisorContractTests(unittest.TestCase):
    def test_event_round_trip_and_strategy_type(self):
        event = SupervisorEventV1(
            event_type=SupervisorEventType.RUN_STARTED, run_id="run-1"
        )
        clone = SupervisorEventV1.model_validate_json(event.model_dump_json())
        self.assertEqual(clone, event)
        self.assertEqual(event.to_strategy_event()["event_type"], "strategy_event")

    def test_event_forbids_extra_and_negative(self):
        with self.assertRaises(ValueError):
            SupervisorEventV1(
                event_type=SupervisorEventType.RUN_STARTED, run_id="run-1", extra="x"
            )
        with self.assertRaises(ValueError):
            SupervisorEventV1(
                event_type=SupervisorEventType.RUN_STARTED, run_id="run-1", attempt=-1
            )


if __name__ == "__main__":
    unittest.main()
