"""S6 固定样本与生产入站隔离测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioSubmission,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from tests.support.s6_scenario_samples import (
    build_s6_samples,
    sample_by_id,
    submission_from_sample,
)


class ScenarioSamplesTests(unittest.TestCase):
    def test_builds_24_samples_with_three_states_per_pack(self) -> None:
        samples = build_s6_samples()
        self.assertEqual(len(samples), 24)
        self.assertEqual(len({sample.sample_id for sample in samples}), 24)
        self.assertEqual(
            {sample.expected_completion_status for sample in samples},
            {
                CompletionStatus.COMPLETE,
                CompletionStatus.WAITING_INPUT,
                CompletionStatus.PARTIAL,
            },
        )

    def test_sample_conversion_drops_every_expected_field(self) -> None:
        sample = sample_by_id("growth_experiment.waiting-funnel/1")
        submission = submission_from_sample(sample)
        self.assertIsInstance(submission, ScenarioSubmission)
        self.assertFalse(hasattr(submission, "sample_id"))
        self.assertFalse(hasattr(submission, "expected_completion_status"))
        self.assertFalse(hasattr(submission, "expected_deliverable_ids"))
        self.assertFalse(hasattr(submission, "expected_warning_codes"))


__all__ = ["ScenarioSamplesTests"]
