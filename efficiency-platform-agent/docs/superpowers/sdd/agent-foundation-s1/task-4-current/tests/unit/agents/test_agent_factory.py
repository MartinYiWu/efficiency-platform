from __future__ import annotations

import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from efficiency_platform_agent.agents.errors import (
    AgentAssemblyError,
    AgentInstanceMismatchError,
    AgentNotFoundError,
)
from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.agents.validation import AgentValidator
from tests.support.agent_fakes import build_synthetic_agent, build_synthetic_spec


class RecordingValidator(AgentValidator):
    """记录实例校验调用，用于验证 Factory 的装配顺序。"""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def validate_instance(self, spec, plugin) -> None:
        self._events.append("validate")
        super().validate_instance(spec, plugin)


class AgentFactoryTest(unittest.TestCase):
    def test_create_builds_and_validates_registered_agent(self) -> None:
        registry = AgentRegistry()
        expected = build_synthetic_agent()
        registry.register(expected.spec, lambda: expected)

        actual = AgentFactory(registry).create(expected.spec.agent_id)

        self.assertIs(actual, expected)

    def test_create_preserves_unknown_id_error(self) -> None:
        with self.assertRaises(AgentNotFoundError):
            AgentFactory(AgentRegistry()).create("missing_agent")

    def test_create_wraps_builder_failure_without_leaking_original_details(self) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec()
        original = RuntimeError("包含内部细节的合成异常")

        def failing_builder():
            raise original

        registry.register(spec, failing_builder)
        with self.assertRaises(AgentAssemblyError) as caught:
            AgentFactory(registry).create(spec.agent_id)

        self.assertNotIn("内部细节", str(caught.exception))
        self.assertIs(caught.exception.__cause__, original)

    def test_create_wraps_non_plugin_builder_result(self) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec()
        registry.register(spec, lambda: object())

        with self.assertRaises(AgentAssemblyError) as caught:
            AgentFactory(registry).create(spec.agent_id)

        self.assertNotIn("object", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, AgentInstanceMismatchError)

    def test_create_wraps_registered_spec_mismatch(self) -> None:
        registry = AgentRegistry()
        registered_spec = build_synthetic_spec()
        instance = build_synthetic_agent(
            build_synthetic_spec(agent_id="different_agent")
        )
        registry.register(registered_spec, lambda: instance)

        with self.assertRaises(AgentAssemblyError) as caught:
            AgentFactory(registry).create(registered_spec.agent_id)

        self.assertNotIn("different_agent", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, AgentInstanceMismatchError)

    def test_create_validates_only_after_builder_returns(self) -> None:
        events: list[str] = []
        registry = AgentRegistry()
        spec = build_synthetic_spec()

        def builder():
            events.append("build")
            return build_synthetic_agent(spec)

        registry.register(spec, builder)
        AgentFactory(registry, RecordingValidator(events)).create(spec.agent_id)

        self.assertEqual(events, ["build", "validate"])


if __name__ == "__main__":
    unittest.main()
