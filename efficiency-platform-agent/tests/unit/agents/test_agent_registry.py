from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))


from efficiency_platform_agent.agents.errors import (
    AgentNotFoundError,
    AgentRegistrationConflictError,
)
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import AgentKind
from tests.support.agent_fakes import build_synthetic_agent, build_synthetic_spec


class AgentRegistryTest(unittest.TestCase):
    def test_match_requires_all_capabilities_and_one_optional_capability(self) -> None:
        registry = AgentRegistry()
        spec_b = build_synthetic_spec(
            "agent_b",
            frozenset({"content", "wechat"}),
        )
        spec_a = build_synthetic_spec(
            "agent_a",
            frozenset({"content", "xiaohongshu"}),
        )
        registry.register(spec_b, lambda: build_synthetic_agent(spec_b))
        registry.register(spec_a, lambda: build_synthetic_agent(spec_a))

        matches = registry.match(
            CapabilityRequirement(
                all_of=frozenset({"content"}),
                any_of=frozenset({"xiaohongshu", "wechat"}),
            )
        )

        self.assertEqual(
            tuple(item.spec.agent_id for item in matches),
            ("agent_a", "agent_b"),
        )

    def test_duplicate_agent_id_fails_closed(self) -> None:
        registry = AgentRegistry()
        spec_a = build_synthetic_spec("agent_a", frozenset({"content"}))
        registry.register(spec_a, lambda: build_synthetic_agent(spec_a))

        with self.assertRaises(AgentRegistrationConflictError):
            duplicate = build_synthetic_spec(
                "agent_a",
                frozenset({"research"}),
            )
            registry.register(
                duplicate,
                lambda: build_synthetic_agent(duplicate),
            )

    def test_get_raises_for_an_unregistered_agent_id(self) -> None:
        with self.assertRaises(AgentNotFoundError):
            AgentRegistry().get("missing_agent")

    def test_match_returns_an_empty_tuple_when_no_capability_matches(self) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec("agent_a", frozenset({"content"}))
        registry.register(spec, lambda: build_synthetic_agent(spec))

        matches = registry.match(CapabilityRequirement(all_of=frozenset({"research"})))

        self.assertEqual(matches, ())

    def test_match_returns_empty_when_any_capability_is_completely_unmatched(
        self,
    ) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec("agent_a", frozenset({"content"}))
        registry.register(spec, lambda: build_synthetic_agent(spec))

        matches = registry.match(
            CapabilityRequirement(
                all_of=frozenset({"content"}),
                any_of=frozenset({"research", "analytics"}),
            )
        )

        self.assertEqual(matches, ())

    def test_match_can_filter_by_agent_kind(self) -> None:
        registry = AgentRegistry()
        specialist = build_synthetic_spec("specialist_a", frozenset({"content"}))
        supervisor = replace(
            specialist, agent_id="supervisor_a", kind=AgentKind.SUPERVISOR
        )
        registry.register(specialist, lambda: build_synthetic_agent(specialist))
        registry.register(supervisor, lambda: build_synthetic_agent(supervisor))

        matches = registry.match(
            CapabilityRequirement(all_of=frozenset({"content"})),
            kind=AgentKind.SUPERVISOR,
        )

        self.assertEqual(
            tuple(item.spec.agent_id for item in matches),
            ("supervisor_a",),
        )

    def test_snapshot_is_an_immutable_copy_of_current_registrations(self) -> None:
        registry = AgentRegistry()
        spec_a = build_synthetic_spec("agent_a", frozenset({"content"}))
        registry.register(spec_a, lambda: build_synthetic_agent(spec_a))

        snapshot = registry.snapshot()
        spec_b = build_synthetic_spec("agent_b", frozenset({"research"}))
        registry.register(spec_b, lambda: build_synthetic_agent(spec_b))

        self.assertIsInstance(snapshot, MappingProxyType)
        self.assertEqual(tuple(snapshot), ("agent_a",))
        with self.assertRaises(TypeError):
            snapshot["agent_b"] = registry.get("agent_b")

    def test_register_rejects_a_non_callable_builder(self) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec("agent_a", frozenset({"content"}))

        with self.assertRaises(TypeError):
            registry.register(spec, object())

    def test_duplicate_registration_preserves_original_entry_and_does_not_build(
        self,
    ) -> None:
        registry = AgentRegistry()
        original_spec = build_synthetic_spec("agent_a", frozenset({"content"}))
        replacement_spec = build_synthetic_spec("agent_a", frozenset({"research"}))
        original_builder_calls = 0
        replacement_builder_calls = 0

        def original_builder():
            nonlocal original_builder_calls
            original_builder_calls += 1
            return build_synthetic_agent(original_spec)

        def replacement_builder():
            nonlocal replacement_builder_calls
            replacement_builder_calls += 1
            return build_synthetic_agent(replacement_spec)

        registry.register(original_spec, original_builder)
        with self.assertRaises(AgentRegistrationConflictError):
            registry.register(replacement_spec, replacement_builder)

        registration = registry.get("agent_a")
        self.assertEqual(registration.spec, original_spec)
        self.assertEqual(original_builder_calls, 0)
        self.assertEqual(replacement_builder_calls, 0)


if __name__ == "__main__":
    unittest.main()
