"""S6 场景质量门禁的固定离线测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.deliverables import (
    DeliverableBundle,
    DeliverableKind,
    GenerationProcessReference,
    OperationDeliverable,
)
from efficiency_platform_agent.agents.operation.scenarios.contracts import (
    ScenarioExecutionResult,
)
from efficiency_platform_agent.agents.operation.scenarios.manifests import (
    build_s6_manifests,
)
from efficiency_platform_agent.agents.operation.scenarios.quality import (
    DeterministicScenarioQualityGate,
)
from efficiency_platform_agent.core.multi_agent import CompletionStatus
from efficiency_platform_agent.core.run import JsonObject


def _bundle(fingerprints: tuple[str, ...]) -> DeliverableBundle:
    items = tuple(
        OperationDeliverable(
            "operation-deliverable/1",
            f"deliverable-{index}",
            DeliverableKind.COPY,
            "1.0.0",
            f"标题-{index}",
            ("subject",),
            ("channel",),
            None,
            JsonObject(
                (
                    ("body_fingerprint", fingerprint),
                    ("headline", f"headline-{index}"),
                    ("structure_id", f"structure-{index}"),
                )
            ),
            frozenset(),
            frozenset(),
            frozenset(),
            (),
            GenerationProcessReference(f"process-{index}", "1.0.0", (), ()),
            None,
            None,
            "plan-a",
            None,
            None,
        )
        for index, fingerprint in enumerate(fingerprints, start=1)
    )
    return DeliverableBundle(
        "deliverable-bundle/1",
        "bundle-a",
        "multi_platform_content",
        "plan-a",
        items,
        None,
        (),
        frozenset(),
    )


class ScenarioQualityGateTests(unittest.TestCase):
    """验证多平台共享事实时仍要求独立创作。"""

    def _result(self, bundle: DeliverableBundle) -> ScenarioExecutionResult:
        return ScenarioExecutionResult(
            "multi_platform_content",
            "1.0.0",
            CompletionStatus.COMPLETE,
            bundle,
            None,
            (),
            ("content",),
            (),
            frozenset(),
            None,
        )

    def test_multi_platform_rejects_copied_body(self) -> None:
        manifest = next(
            item
            for item in build_s6_manifests()
            if item.scenario_id == "multi_platform_content"
        )
        report = DeterministicScenarioQualityGate().validate(
            manifest, self._result(_bundle(("same", "same", "distinct")))
        )
        self.assertEqual(report.checks[6].status, report.checks[6].status.FAILED)

    def test_multi_platform_accepts_distinct_fingerprints(self) -> None:
        manifest = next(
            item
            for item in build_s6_manifests()
            if item.scenario_id == "multi_platform_content"
        )
        report = DeterministicScenarioQualityGate().validate(
            manifest, self._result(_bundle(("a", "b", "c")))
        )
        self.assertEqual(report.checks[6].status, report.checks[6].status.PASSED)


if __name__ == "__main__":
    unittest.main()
