from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError


class AgentSpecTest(unittest.TestCase):
    def test_agent_spec_is_immutable_and_requires_complete_metadata(self) -> None:
        from efficiency_platform_agent.core.agent import AgentSpec
        from efficiency_platform_agent.core.enums import AgentKind, StrategyMode

        from efficiency_platform_agent.core.run import ExecutionBudget

        budget = ExecutionBudget(
            max_iterations=3,
            max_tool_calls=2,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            timeout_ms=30_000,
            max_cost_microunits=0,
        )
        spec = AgentSpec(
            agent_id="synthetic_research_agent",
            semantic_version="1.0.0",
            owner="agent_platform",
            kind=AgentKind.SPECIALIST,
            capability_ids=frozenset({"public_research"}),
            supported_task_types=frozenset({"research"}),
            input_schema_version="research-task/1",
            output_schema_version="research-result/1",
            state_schema_version="research-state/1",
            checkpoint_version="research-checkpoint/1",
            allowed_strategies=frozenset({StrategyMode.REACT}),
            prompt_bundle_id="research_prompt/1",
            allowed_tools=frozenset({"public_search"}),
            knowledge_scopes=frozenset({"public"}),
            memory_policy_id="specialist_memory/1",
            model_policy_id="adaptive_model/1",
            quality_policy_id="research_quality/1",
            permissions=frozenset({"public_web.read"}),
            budget=budget,
            termination_conditions=frozenset({"succeeded", "failed"}),
        )

        self.assertEqual(spec.agent_id, "synthetic_research_agent")
        with self.assertRaises(FrozenInstanceError):
            spec.owner = "changed"
        with self.assertRaises(ValueError):
            AgentSpec(
                agent_id="synthetic_research_agent",
                semantic_version="1.0.0",
                owner="agent_platform",
                kind=AgentKind.SPECIALIST,
                capability_ids=frozenset(),
                supported_task_types=frozenset({"research"}),
                input_schema_version="research-task/1",
                output_schema_version="research-result/1",
                state_schema_version="research-state/1",
                checkpoint_version="research-checkpoint/1",
                allowed_strategies=frozenset({StrategyMode.REACT}),
                prompt_bundle_id="research_prompt/1",
                allowed_tools=frozenset(),
                knowledge_scopes=frozenset(),
                memory_policy_id="specialist_memory/1",
                model_policy_id="adaptive_model/1",
                quality_policy_id="research_quality/1",
                permissions=frozenset(),
                budget=budget,
                termination_conditions=frozenset({"failed"}),
            )

    def test_capability_requirement_uses_all_of_and_any_of_semantics(self) -> None:
        from efficiency_platform_agent.core.agent import CapabilityRequirement

        requirement = CapabilityRequirement(
            all_of=frozenset({"content_creation"}),
            any_of=frozenset({"xiaohongshu", "wechat_official_account"}),
        )

        self.assertEqual(requirement.all_of, frozenset({"content_creation"}))
        with self.assertRaises(ValueError):
            CapabilityRequirement(all_of=frozenset(), any_of=frozenset())


if __name__ == "__main__":
    unittest.main()
