### Task 4: 建立 Agent Factory 装配边界

**Files:**
- Create: `src/efficiency_platform_agent/agents/factory.py`
- Create: `tests/unit/agents/test_agent_factory.py`

**Interfaces:**
- Consumes: `AgentRegistry.get()`、`RegisteredAgent.builder`、`AgentValidator.validate_instance()`。
- Produces: `AgentFactory.create(agent_id: str) -> AgentPlugin`。

- [ ] **Step 1: 编写 Factory 失败测试**

必须覆盖：合法 Builder 返回 Agent；未知 ID；Builder 抛异常；Builder 返回非 AgentPlugin；实例 `spec` 与注册 Spec 不一致。核心测试：

```python
from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.errors import AgentAssemblyError
from efficiency_platform_agent.agents.factory import AgentFactory
from efficiency_platform_agent.agents.registry import AgentRegistry
from tests.support.agent_fakes import (
    build_synthetic_agent,
    build_synthetic_spec,
)


class AgentFactoryTest(unittest.TestCase):
    def test_create_builds_and_validates_registered_agent(self) -> None:
        registry = AgentRegistry()
        expected = build_synthetic_agent()
        registry.register(expected.spec, lambda: expected)

        actual = AgentFactory(registry).create(expected.spec.agent_id)

        self.assertIs(actual, expected)

    def test_create_wraps_builder_failure_without_leaking_original_details(self) -> None:
        registry = AgentRegistry()
        spec = build_synthetic_spec()

        def failing_builder():
            raise RuntimeError("包含内部细节的合成异常")

        registry.register(spec, failing_builder)
        with self.assertRaises(AgentAssemblyError) as caught:
            AgentFactory(registry).create(spec.agent_id)

        self.assertNotIn("内部细节", str(caught.exception))
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_factory -v
```

Expected: FAIL，指出 `agents.factory` 不存在。

- [ ] **Step 3: 实现 AgentFactory**

```python
from __future__ import annotations

from efficiency_platform_agent.core.ports import AgentPlugin

from .errors import AgentAssemblyError, AgentDefinitionError
from .registry import AgentRegistry
from .validation import AgentValidator


class AgentFactory:
    """从显式注册定义创建并校验 AgentPlugin。"""

    def __init__(
        self,
        registry: AgentRegistry,
        validator: AgentValidator | None = None,
    ) -> None:
        self._registry = registry
        self._validator = validator or AgentValidator()

    def create(self, agent_id: str) -> AgentPlugin:
        registration = self._registry.get(agent_id)
        try:
            plugin = registration.builder()
        except Exception as error:
            raise AgentAssemblyError(f"Agent 装配失败: {agent_id}") from error
        try:
            self._validator.validate_instance(registration.spec, plugin)
        except AgentDefinitionError as error:
            raise AgentAssemblyError(f"Agent 实例校验失败: {agent_id}") from error
        return plugin
```

执行顺序固定为：Registry 查找 → 调用 Builder → 捕获并归一化 Builder 错误 → Validator 校验实例 → 返回。`AgentNotFoundError` 原样保留；Builder 的内部异常使用 `raise AgentAssemblyError(safe_message) from error` 保留内部异常链但不在安全消息中泄露细节。

- [ ] **Step 4: 运行 Factory、Registry 和 Validator 测试**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_factory tests.unit.agents.test_agent_registry tests.unit.agents.test_agent_validation -v
```

Expected: PASS。

- [ ] **Step 5: 保存任务评审证据**

记录装配失败矩阵和错误安全性；不得声称依赖注入容器、Graph 编译或 Provider 装配已完成。

