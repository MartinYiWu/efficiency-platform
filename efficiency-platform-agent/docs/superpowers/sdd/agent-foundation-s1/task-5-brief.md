### Task 5: 建立可复用 Agent 测试套件和契约准入测试

**Files:**
- Create: `tests/contract/__init__.py`
- Create: `tests/contract/agents/__init__.py`
- Create: `tests/contract/agents/test_agent_plugin_contract.py`

**Interfaces:**
- Consumes: S1 的 AgentSpec、AgentPlugin、Registry、Factory 和现有 Run/SupervisorTask 契约。
- Produces: 从显式注册到异步执行的可复用准入契约测试。

- [ ] **Step 1: 创建契约测试包并编写准入测试**

创建空的 `tests/contract/__init__.py` 和 `tests/contract/agents/__init__.py`，并在 `test_agent_plugin_contract.py` 写入：

```python
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
```

该测试通过标准库 `IsolatedAsyncioTestCase` 验证显式注册、能力匹配、Factory 装配、结构化 SupervisorTask 输入和结构化 RunResult 输出。合成 Agent 的实现没有网络、数据库、缓存、对象存储或模型依赖。

- [ ] **Step 2: 运行契约测试并确认失败**

Run:

```powershell
uv run python -m unittest tests.contract.agents.test_agent_plugin_contract -v
```

Expected: 如果 Task 1～4 已完成则 PASS；若失败，只能修复 S1 契约或测试数据工厂，不得通过访问外部系统绕过。所有测试数据必须是合成值，不放入真实账号、URL、连接串、Prompt 或业务数据。

- [ ] **Step 3: 运行全部 S1 单元与契约测试**

Run:

```powershell
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: PASS，输出包含新增 Agent Spec、Validator、Registry、Factory 和 Plugin 契约测试；不得访问真实网络、数据库、Redis、COS 或模型。

- [ ] **Step 4: 保存任务评审证据**

记录测试总数、耗时和外部依赖为零的证据；明确这只证明 S1 离线契约，不证明业务 Agent 或真实 Provider。

