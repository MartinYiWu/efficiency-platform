### Task 3: 建立显式 Agent Registry 和能力匹配

**Files:**
- Create: `src/efficiency_platform_agent/agents/registry.py`
- Create: `tests/unit/agents/test_agent_registry.py`

**Interfaces:**
- Consumes: `AgentSpec`、`CapabilityRequirement`、`AgentValidator`、`AgentRegistrationConflictError`、`AgentNotFoundError`。
- Produces: `AgentBuilder`、`RegisteredAgent`、`AgentRegistry.register()`、`AgentRegistry.get()`、`AgentRegistry.match()`、`AgentRegistry.snapshot()`。

- [ ] **Step 1: 编写 Registry 失败测试**

至少覆盖：

```python
from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.errors import (
    AgentRegistrationConflictError,
)
from efficiency_platform_agent.agents.registry import AgentRegistry
from efficiency_platform_agent.core.agent import CapabilityRequirement
from tests.support.agent_fakes import (
    build_synthetic_agent,
    build_synthetic_spec,
)


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

        self.assertEqual(tuple(item.spec.agent_id for item in matches), ("agent_a", "agent_b"))

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
```

同时测试不存在 ID、无匹配能力、注册快照不可变和结果按 `agent_id` 稳定排序。

- [ ] **Step 2: 运行测试并确认失败**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_registry -v
```

Expected: FAIL，指出 `agents.registry` 不存在。

- [ ] **Step 3: 实现 Registry 数据结构**

实现：

```python
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias

from efficiency_platform_agent.core.agent import (
    AgentSpec,
    CapabilityRequirement,
)
from efficiency_platform_agent.core.enums import AgentKind
from efficiency_platform_agent.core.ports import AgentPlugin

from .errors import AgentNotFoundError, AgentRegistrationConflictError
from .validation import AgentValidator


AgentBuilder: TypeAlias = Callable[[], AgentPlugin]


@dataclass(frozen=True, slots=True)
class RegisteredAgent:
    """一个已经通过定义校验的显式 Agent 注册项。"""

    spec: AgentSpec
    builder: AgentBuilder


class AgentRegistry:
    """提供确定性 Agent 注册、查找和能力匹配。"""

    def __init__(self, validator: AgentValidator | None = None) -> None:
        self._validator = validator or AgentValidator()
        self._registrations: dict[str, RegisteredAgent] = {}

    def register(self, spec: AgentSpec, builder: AgentBuilder) -> None:
        self._validator.validate_spec(spec)
        if not callable(builder):
            raise TypeError("Agent Builder 必须可调用")
        if spec.agent_id in self._registrations:
            raise AgentRegistrationConflictError(
                f"Agent ID 已注册: {spec.agent_id}"
            )
        self._registrations[spec.agent_id] = RegisteredAgent(spec, builder)

    def get(self, agent_id: str) -> RegisteredAgent:
        try:
            return self._registrations[agent_id]
        except KeyError as error:
            raise AgentNotFoundError(f"Agent 不存在: {agent_id}") from error

    def match(
        self,
        requirement: CapabilityRequirement,
        *,
        kind: AgentKind | None = None,
    ) -> Sequence[RegisteredAgent]:
        matches = []
        for registration in self._registrations.values():
            spec = registration.spec
            if kind is not None and spec.kind is not kind:
                continue
            if not requirement.all_of.issubset(spec.capability_ids):
                continue
            if requirement.any_of and spec.capability_ids.isdisjoint(
                requirement.any_of
            ):
                continue
            matches.append(registration)
        return tuple(sorted(matches, key=lambda item: item.spec.agent_id))

    def snapshot(self) -> Mapping[str, RegisteredAgent]:
        return MappingProxyType(dict(self._registrations))
```

匹配语义：候选能力必须包含 `all_of` 全部能力；`any_of` 非空时至少包含其中一个；指定 `kind` 时必须相同。无匹配结果返回空元组，由调用方决定是否抛出 `AgentNotFoundError`；`get` 对不存在 ID 抛出 `AgentNotFoundError`。`snapshot` 使用 `MappingProxyType` 返回不可修改副本。

明确禁止：`importlib` 动态导入、目录扫描、`__init__.py` 注册副作用、环境变量驱动的隐式覆盖。

- [ ] **Step 4: 运行 Registry 测试**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_registry tests.architecture.test_dependency_rules -v
```

Expected: PASS，匹配顺序稳定且重复注册失败关闭。

- [ ] **Step 5: 保存任务评审证据**

记录注册和匹配行为矩阵；确认没有扫描、动态导入或隐式注册代码。

