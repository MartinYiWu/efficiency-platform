"""后四个运营场景的固定样本与无触达边界回归测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from tests.support.s6_scenario_fakes import RecordingFakeTool
from tests.support.s6_scenario_samples import build_s6_samples, sample_by_id


class LaterScenarioRegressionTests(unittest.TestCase):
    """验证活动、日历、增长和复盘场景的样本边界。"""

    def test_four_later_packs_have_complete_waiting_and_partial_samples(self) -> None:
        samples = build_s6_samples()
        later = {
            "campaign_plan",
            "content_calendar",
            "growth_experiment",
            "operation_review",
        }
        selected = [sample for sample in samples if sample.scenario_id in later]
        self.assertEqual(len(selected), 12)
        for scenario_id in later:
            states = {
                sample.expected_completion_status
                for sample in selected
                if sample.scenario_id == scenario_id
            }
            self.assertEqual(states, {"complete", "waiting_input", "partial"})
            self.assertIsNotNone(sample_by_id(f"{scenario_id}.complete/1"))

    def test_later_pack_manifests_are_declared_without_touch_tools(self) -> None:
        manifest_ids = {manifest.scenario_id for manifest in build_s6_manifests()}
        self.assertTrue(
            {
                "campaign_plan",
                "content_calendar",
                "growth_experiment",
                "operation_review",
            }
            <= manifest_ids
        )
        tool = RecordingFakeTool()
        self.assertFalse(tool.side_effect)
        self.assertEqual(tool.calls, [])


if __name__ == "__main__":
    unittest.main()
