from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.core.agent import CapabilityRequirement
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.core.run import JsonObject, SupervisorTask
from tests.support.agent_fakes import (
    build_synthetic_agent,
    build_synthetic_spec,
)


class AgentPluginContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_registered_specialist_accepts_trimmed_task_and_returns_result(
        self,
    ) -> None:
        spec = build_synthetic_spec()
        registry = AgentRegistry()
        registry.register(spec, lambda: build_synthetic_agent(spec))

        matches = registry.match(
            CapabilityRequirement(all_of=frozenset({"public_research"}))
        )
        self.assertEqual(len(matches), 1)
        plugin = AgentFactory(registry).create(matches[0].spec.agent_id)
        task = SupervisorTask(
            task_id="task-1",
            parent_run_id="run-1",
            target_agent=spec.agent_id,
            input_data=JsonObject((("question", "合成研究问题"),)),
            context_view=JsonObject((("evidence_ids", ("evidence-1",)),)),
            allowed_tools=frozenset({"public_search"}),
            budget=spec.budget,
        )

        result = await plugin.run(task)

        self.assertEqual(result.status, RunStatus.SUCCEEDED)
        self.assertEqual(result.run_id, "run-1")
        self.assertEqual(result.output, JsonObject((("task_id", "task-1"),)))


if __name__ == "__main__":
    unittest.main()
