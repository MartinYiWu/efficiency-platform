"""Specialist 安全派发与结果解码测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.operation.supervisor.budget import BudgetLedger
from efficiency_platform_agent.agents.operation.supervisor.dispatch import (
    DispatchBuilder,
    SpecialistResultDecoder,
)
from efficiency_platform_agent.core.enums import RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    RunResult,
)
from tests.support.supervisor_fakes import (
    build_specialist_spec,
    build_task_node,
    register_specialists,
)


class SpecialistDispatchTest(unittest.TestCase):
    """验证 SupervisorTask 的白名单和结果边界。"""

    def test_dispatch_builds_trimmed_supervisor_task(self) -> None:
        spec = build_specialist_spec("specialist_a")
        registry = register_specialists((spec,))
        node = build_task_node()
        selected = (
            __import__(
                "efficiency_platform_agent.agents.operation.supervisor.selection",
                fromlist=["SpecialistSelector"],
            )
            .SpecialistSelector(registry)
            .rank(node)[0]
        )
        ledger = BudgetLedger.allocate(
            ExecutionBudget(10, 10, 1_000, 1_000, 30_000, 100),
            ((node.task_id, node.requested_budget),),
        )
        dispatch = DispatchBuilder(AgentFactory(registry), ledger).build(
            node,
            selected,
            parent_run_id="run-a",
            parent_deadline_epoch_ms=99,
            input_data=JsonObject((("input", "value"),)),
        )
        self.assertEqual(dispatch.task.target_agent, "specialist_a")
        self.assertEqual(dispatch.task.allowed_tools, node.allowed_tools)
        self.assertEqual(dispatch.parent_deadline_epoch_ms, 99)

    def test_decoder_rejects_unversioned_output(self) -> None:
        result = RunResult(
            run_id="run-a",
            status=RunStatus.SUCCEEDED,
            strategy=StrategyMode.MULTI_AGENT,
            output=JsonObject((("task_id", "synthetic-task"),)),
        )
        with self.assertRaisesRegex(ValueError, "OUTPUT_SCHEMA_INVALID"):
            SpecialistResultDecoder().decode(result)

    def test_decoder_round_trips_versioned_evidence_pack(self) -> None:
        evidence_record = JsonObject(
            (
                ("evidence_id", "evidence-a"),
                ("title", "公开资料"),
                ("publisher", "资料发布者"),
                ("source_url", "https://example.com/source"),
                ("published_at_epoch_ms", 1),
                ("retrieved_at_epoch_ms", 2),
                ("source_scope", "external_reference"),
                ("supported_conclusion_ids", ("conclusion-a",)),
                ("within_time_window", True),
                ("duplicate_status", "unique"),
                ("quality_status", "valid"),
            )
        )
        evidence_pack = JsonObject(
            (
                ("contract_version", "evidence-pack/1"),
                ("pack_id", "pack-a"),
                ("task_id", "synthetic-task"),
                ("records", (evidence_record,)),
                (
                    "supports",
                    (
                        JsonObject(
                            (
                                ("conclusion_id", "conclusion-a"),
                                ("evidence_ids", ("evidence-a",)),
                            )
                        ),
                    ),
                ),
            )
        )
        output = JsonObject(
            (
                ("contract_version", "operation-specialist-result/1"),
                ("task_id", "synthetic-task"),
                ("completed_scope", ("research",)),
                ("missing_scope", ()),
                ("deliverable_bundle", None),
                ("evidence_pack", evidence_pack),
                ("quality_report", None),
                ("assumptions", ()),
                ("warnings", ()),
                ("error_code", None),
                ("requested_capability", None),
                ("revision_request", None),
                ("usage", None),
            )
        )
        result = RunResult(
            "run-a", RunStatus.SUCCEEDED, StrategyMode.MULTI_AGENT, output
        )

        decoded = SpecialistResultDecoder().decode(result)

        self.assertIsNotNone(decoded.evidence_pack)
        assert decoded.evidence_pack is not None
        self.assertEqual(decoded.evidence_pack.records[0].evidence_id, "evidence-a")
        self.assertEqual(
            decoded.evidence_pack.supports[0].evidence_ids, frozenset({"evidence-a"})
        )

    def test_decoder_rejects_negative_specialist_usage(self) -> None:
        output = JsonObject(
            (
                ("contract_version", "operation-specialist-result/1"),
                ("task_id", "synthetic-task"),
                ("completed_scope", ()),
                ("missing_scope", ()),
                ("deliverable_bundle", None),
                ("evidence_pack", None),
                ("quality_report", None),
                ("assumptions", ()),
                ("warnings", ()),
                ("error_code", None),
                ("requested_capability", None),
                ("revision_request", None),
                (
                    "usage",
                    JsonObject(
                        (
                            ("iterations", -1),
                            ("tool_calls", 0),
                            ("input_tokens", 0),
                            ("output_tokens", 0),
                            ("elapsed_ms", 0),
                            ("cost_microunits", 0),
                        )
                    ),
                ),
            )
        )
        with self.assertRaisesRegex(ValueError, "OUTPUT_SCHEMA_INVALID:usage"):
            SpecialistResultDecoder().decode(
                RunResult(
                    "run-a", RunStatus.SUCCEEDED, StrategyMode.MULTI_AGENT, output
                )
            )


if __name__ == "__main__":
    unittest.main()
