from __future__ import annotations

import unittest

from efficiency_platform_agent.contracts.operation_resume import (
    OperationResumeValidator,
)
from efficiency_platform_agent.core.run import JsonObject
from efficiency_platform_agent.orchestration.contracts import CheckpointView


class OperationSupervisorResumeTests(unittest.TestCase):
    def test_stale_resume_value_is_rejected(self):
        checkpoint = CheckpointView(
            "run-1",
            "s2:multi_agent:1",
            "cp-1",
            JsonObject(
                (("request_id", "req-1"), ("plan_revision", 0), ("fence_token", 1))
            ),
        )
        with self.assertRaisesRegex(ValueError, "STALE_RESUME_INPUT"):
            OperationResumeValidator().validate(
                checkpoint,
                JsonObject(
                    (
                        ("contract_version", "operation-resume/1"),
                        ("request_id", "req-other"),
                        ("plan_revision", 0),
                        ("supplemental", JsonObject()),
                        ("fence_token", 1),
                    )
                ),
            )

    def test_resume_value_requires_versioned_complete_shape(self):
        checkpoint = CheckpointView(
            "run-1",
            "s2:multi_agent:1",
            "cp-1",
            JsonObject(
                (("request_id", "req-1"), ("plan_revision", 0), ("fence_token", 1))
            ),
        )
        with self.assertRaisesRegex(ValueError, "RESUME_VALUE_INVALID"):
            OperationResumeValidator().validate(
                checkpoint,
                JsonObject((("request_id", "req-1"),)),
            )

    def test_resume_value_rejects_unknown_fields(self):
        checkpoint = CheckpointView(
            "run-1",
            "s2:multi_agent:1",
            "cp-1",
            JsonObject(
                (("request_id", "req-1"), ("plan_revision", 0), ("fence_token", 1))
            ),
        )
        with self.assertRaisesRegex(ValueError, "RESUME_VALUE_INVALID"):
            OperationResumeValidator().validate(
                checkpoint,
                JsonObject(
                    (
                        ("contract_version", "operation-resume/1"),
                        ("request_id", "req-1"),
                        ("plan_revision", 0),
                        ("supplemental", JsonObject()),
                        ("fence_token", 1),
                        ("unexpected", True),
                    )
                ),
            )


if __name__ == "__main__":
    unittest.main()
