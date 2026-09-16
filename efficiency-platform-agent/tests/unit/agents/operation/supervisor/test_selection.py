"""Specialist 元数据选择和上下文裁剪测试。"""

from __future__ import annotations

import unittest
from typing import cast

from efficiency_platform_agent.agents.operation.supervisor.selection import (
    ContextProjector,
    SpecialistSelector,
)
from efficiency_platform_agent.core.enums import AgentKind
from efficiency_platform_agent.core.run import JsonObject
from tests.support.supervisor_fakes import (
    build_specialist_spec,
    build_task_node,
    register_specialists,
)


class _RecordingRegistry:
    """记录 Registry 调用并委托到真实 Registry。"""

    def __init__(self, specs: tuple[object, ...]) -> None:
        self._registry = register_specialists(specs)  # type: ignore[arg-type]
        self.match_calls: list[tuple[object, AgentKind | None]] = []

    def match(self, requirement: object, *, kind: AgentKind | None = None) -> object:
        self.match_calls.append((requirement, kind))
        return self._registry.match(requirement, kind=kind)  # type: ignore[arg-type]


class SpecialistSelectionTest(unittest.TestCase):
    """验证六维硬过滤、稳定排序和上下文边界。"""

    def test_selector_uses_registry_metadata_without_business_agent_ids(self) -> None:
        specs = (
            build_specialist_spec("specialist_a"),
            build_specialist_spec(
                "specialist_b",
                capability_ids=frozenset({"synthetic.compose", "synthetic.extra"}),
                allowed_tools=frozenset({"synthetic.read", "synthetic.extra"}),
                permissions=frozenset({"public.read", "public.extra"}),
            ),
            build_specialist_spec(
                "wrong_type", supported_task_types=frozenset({"other"})
            ),
        )
        registry = _RecordingRegistry(specs)
        ranked = SpecialistSelector(registry).rank(build_task_node())  # type: ignore[arg-type]
        self.assertEqual(
            tuple(item.agent_id for item in ranked), ("specialist_a", "specialist_b")
        )
        self.assertEqual(registry.match_calls[0][1], AgentKind.SPECIALIST)

    def test_selector_filters_schema_permission_tool_and_capability_mismatch(
        self,
    ) -> None:
        specs = (
            build_specialist_spec("good"),
            build_specialist_spec("bad_schema", input_schema_version="other/1"),
            build_specialist_spec("bad_permission", permissions=frozenset()),
            build_specialist_spec("bad_tool", allowed_tools=frozenset()),
            build_specialist_spec(
                "bad_capability", capability_ids=frozenset({"other"})
            ),
        )
        ranked = SpecialistSelector(register_specialists(specs)).rank(build_task_node())
        self.assertEqual(tuple(item.agent_id for item in ranked), ("good",))

    def test_context_projector_keeps_only_requested_profile_references(self) -> None:
        from efficiency_platform_agent.agents.operation.contracts.profiles import (
            OperationContext,
            ProfileKind,
            ProfileReference,
        )
        from efficiency_platform_agent.agents.operation.contracts.task import (
            SourceScope,
        )

        context = OperationContext(
            contract_version="operation-context/1",
            context_id="context-a",
            tenant_id="tenant-a",
            task_id="task-a",
            profile_references=(
                ProfileReference("brand-a", ProfileKind.BRAND, "1.0.0", ("fact-a",)),
                ProfileReference(
                    "channel-a", ProfileKind.CHANNEL, "1.0.0", ("fact-b",)
                ),
            ),
            source_scope_ids=frozenset({SourceScope.USER_INPUT, SourceScope.PROFILE}),
        )
        projected = ContextProjector().project(
            context,
            profile_ids=("brand-a",),
            source_scopes=frozenset({SourceScope.USER_INPUT}),
        )
        self.assertIsInstance(projected, JsonObject)
        values = dict(projected.items)
        profile_values = cast(
            tuple[tuple[object, ...], ...], values["profile_references"]
        )
        self.assertEqual(tuple(item[0] for item in profile_values), ("brand-a",))
        self.assertEqual(values["source_scope_ids"], ("user_input",))
        with self.assertRaises(ValueError):
            ContextProjector().project(
                context,
                profile_ids=("missing",),
                source_scopes=frozenset({SourceScope.USER_INPUT}),
            )


if __name__ == "__main__":
    unittest.main()
