from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from efficiency_platform_agent.agents.errors import (
    AgentDefinitionError,
    AgentInstanceMismatchError,
)
from efficiency_platform_agent.agents.validation import AgentValidator
from efficiency_platform_agent.core.run import ExecutionBudget
from tests.support.agent_fakes import build_synthetic_agent, build_synthetic_spec


class AgentValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = AgentValidator()

    def test_validate_spec_accepts_valid_spec(self) -> None:
        self.validator.validate_spec(build_synthetic_spec())

    def test_core_contract_rejects_missing_required_spec_fields(self) -> None:
        cases = (
            ("capability_ids", frozenset(), ValueError),
            ("input_schema_version", "", ValueError),
            ("allowed_strategies", frozenset(), ValueError),
            ("termination_conditions", frozenset(), ValueError),
        )

        for field_name, value, error_type in cases:
            with self.subTest(field_name=field_name), self.assertRaises(error_type):
                replace(build_synthetic_spec(), **{field_name: value})

    def test_validate_spec_rejects_non_agent_spec(self) -> None:
        with self.assertRaises(AgentDefinitionError):
            self.validator.validate_spec(object())

    def test_validate_instance_rejects_non_plugin(self) -> None:
        with self.assertRaises(AgentInstanceMismatchError):
            self.validator.validate_instance(build_synthetic_spec(), object())

    def test_validate_instance_rejects_non_callable_run(self) -> None:
        agent = build_synthetic_agent()
        plugin = SimpleNamespace(
            descriptor=agent.descriptor,
            spec=agent.spec,
            run=1,
        )

        with self.assertRaises(AgentInstanceMismatchError) as caught:
            self.validator.validate_instance(agent.spec, plugin)

        self.assertIn("run", str(caught.exception))

    def test_validate_instance_rejects_synchronous_run(self) -> None:
        agent = build_synthetic_agent()

        def synchronous_run():
            return None

        plugin = SimpleNamespace(
            descriptor=agent.descriptor,
            spec=agent.spec,
            run=synchronous_run,
        )

        with self.assertRaises(AgentInstanceMismatchError) as caught:
            self.validator.validate_instance(agent.spec, plugin)

        self.assertIn("run", str(caught.exception))

    def test_validate_instance_rejects_non_descriptor(self) -> None:
        plugin = build_synthetic_agent()
        plugin.descriptor = SimpleNamespace(
            name=plugin.spec.agent_id,
            semantic_version=plugin.spec.semantic_version,
            input_schema_version=plugin.spec.input_schema_version,
            output_schema_version=plugin.spec.output_schema_version,
            permissions=plugin.spec.permissions,
            budget=plugin.spec.budget,
            termination_conditions=plugin.spec.termination_conditions,
            checkpoint_version=plugin.spec.checkpoint_version,
        )

        with self.assertRaises(AgentInstanceMismatchError):
            self.validator.validate_instance(plugin.spec, plugin)

    def test_validate_instance_rejects_plugin_spec_mismatch(self) -> None:
        plugin = build_synthetic_agent()

        with self.assertRaises(AgentInstanceMismatchError) as caught:
            self.validator.validate_instance(
                replace(plugin.spec, agent_id="another_agent"), plugin
            )

        self.assertIn("spec", str(caught.exception))

    def test_validate_instance_rejects_descriptor_spec_mismatch(self) -> None:
        validator = AgentValidator()
        plugin = build_synthetic_agent(descriptor_name="different_agent")

        with self.assertRaises(AgentInstanceMismatchError) as caught:
            validator.validate_instance(plugin.spec, plugin)

        self.assertIn("agent_id", str(caught.exception))

    def test_validate_instance_rejects_each_descriptor_contract_mismatch(self) -> None:
        spec = build_synthetic_spec()
        different_budget = ExecutionBudget(
            max_iterations=4,
            max_tool_calls=2,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            timeout_ms=30_000,
            max_cost_microunits=0,
        )
        cases = (
            ("semantic_version", "2.0.0"),
            ("input_schema_version", "different-input/1"),
            ("output_schema_version", "different-output/1"),
            ("permissions", frozenset({"different.read"})),
            ("budget", different_budget),
            ("termination_conditions", frozenset({"failed"})),
            ("checkpoint_version", "different-checkpoint/1"),
        )

        for field_name, value in cases:
            with self.subTest(field_name=field_name):
                plugin = build_synthetic_agent(spec)
                plugin.descriptor = replace(plugin.descriptor, **{field_name: value})

                with self.assertRaises(AgentInstanceMismatchError) as caught:
                    self.validator.validate_instance(spec, plugin)

                self.assertIn(field_name, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
