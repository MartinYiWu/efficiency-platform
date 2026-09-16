### Task 1: 建立 Agent 与能力的核心契约

**Files:**
- Modify: `src/efficiency_platform_agent/core/enums.py`
- Create: `src/efficiency_platform_agent/core/agent.py`
- Modify: `src/efficiency_platform_agent/core/ports.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/agents/__init__.py`
- Create: `tests/unit/agents/test_agent_spec.py`
- Modify: `tests/architecture/test_core_contracts.py`

**Interfaces:**
- Consumes: 现有 `ExtensionDescriptor`、`StrategyMode`、`AgentPlugin.run(SupervisorTask)`。
- Produces: `AgentKind`、`CapabilitySpec`、`CapabilityRequirement`、`AgentSpec`，以及带 `spec: AgentSpec` 的 `AgentPlugin`。

- [ ] **Step 1: 创建目录级测试包**

创建空的 `tests/unit/__init__.py` 和 `tests/unit/agents/__init__.py`，使标准库 `unittest` 可以稳定发现测试。

- [ ] **Step 2: 编写核心契约失败测试**

在 `tests/unit/agents/test_agent_spec.py` 写入：

```python
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
```

在 `tests/architecture/test_core_contracts.py` 的 `CoreContractsTest` 增加：

```python
    def test_agent_plugin_exposes_versioned_agent_spec(self) -> None:
        from efficiency_platform_agent.core.agent import AgentSpec
        from efficiency_platform_agent.core.ports import AgentPlugin

        self.assertIs(AgentPlugin.__annotations__.get("spec"), AgentSpec)
```

- [ ] **Step 3: 运行测试并确认按预期失败**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_spec tests.architecture.test_core_contracts -v
```

Expected: FAIL，错误指出 `efficiency_platform_agent.core.agent` 或 `AgentKind` 不存在；不得因为测试导入错误以外的原因跳过。

- [ ] **Step 4: 实现最小核心契约**

在 `core/enums.py` 增加：

```python
class AgentKind(StrEnum):
    """Agent 在受控多 Agent 拓扑中的稳定角色。"""

    SUPERVISOR = "supervisor"
    SPECIALIST = "specialist"
```

创建 `core/agent.py`。实现必须使用冻结、带 slots 的 dataclass，并包含：

```python
from __future__ import annotations

import re
from dataclasses import dataclass

from .enums import AgentKind, StrategyMode
from .run import ExecutionBudget


_STABLE_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_SEMANTIC_VERSION = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _require_stable_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ValueError(f"{field_name} must be a stable lowercase identifier")


def _require_non_empty(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_string_set(
    field_name: str,
    value: frozenset[str],
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(value, frozenset):
        raise TypeError(f"{field_name} must be a frozenset")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    for item in value:
        _require_stable_id(field_name, item)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    """可由 Registry 匹配的版本化能力声明。"""

    capability_id: str
    semantic_version: str
    owner: str
    input_schema_version: str
    output_schema_version: str
    permissions: frozenset[str]

    def __post_init__(self) -> None:
        _require_stable_id("capability_id", self.capability_id)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version must use MAJOR.MINOR.PATCH")
        _require_non_empty("owner", self.owner)
        _require_non_empty("input_schema_version", self.input_schema_version)
        _require_non_empty("output_schema_version", self.output_schema_version)
        _require_string_set("permissions", self.permissions, allow_empty=True)


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    """Supervisor 对 Specialist 能力的确定性匹配条件。"""

    all_of: frozenset[str] = frozenset()
    any_of: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_string_set("all_of", self.all_of, allow_empty=True)
        _require_string_set("any_of", self.any_of, allow_empty=True)
        if not self.all_of and not self.any_of:
            raise ValueError("at least one capability requirement must be present")


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Agent 注册、装配和治理所需的完整框架中立定义。"""

    agent_id: str
    semantic_version: str
    owner: str
    kind: AgentKind
    capability_ids: frozenset[str]
    supported_task_types: frozenset[str]
    input_schema_version: str
    output_schema_version: str
    state_schema_version: str
    checkpoint_version: str
    allowed_strategies: frozenset[StrategyMode]
    prompt_bundle_id: str
    allowed_tools: frozenset[str]
    knowledge_scopes: frozenset[str]
    memory_policy_id: str
    model_policy_id: str
    quality_policy_id: str
    permissions: frozenset[str]
    budget: ExecutionBudget
    termination_conditions: frozenset[str]

    def __post_init__(self) -> None:
        _require_stable_id("agent_id", self.agent_id)
        if not _SEMANTIC_VERSION.fullmatch(self.semantic_version):
            raise ValueError("semantic_version must use MAJOR.MINOR.PATCH")
        _require_non_empty("owner", self.owner)
        if not isinstance(self.kind, AgentKind):
            raise TypeError("kind must be an AgentKind")
        _require_string_set("capability_ids", self.capability_ids, allow_empty=False)
        _require_string_set(
            "supported_task_types",
            self.supported_task_types,
            allow_empty=False,
        )
        for field_name in (
            "input_schema_version",
            "output_schema_version",
            "state_schema_version",
            "checkpoint_version",
            "prompt_bundle_id",
            "memory_policy_id",
            "model_policy_id",
            "quality_policy_id",
        ):
            _require_non_empty(field_name, getattr(self, field_name))
        if not isinstance(self.allowed_strategies, frozenset):
            raise TypeError("allowed_strategies must be a frozenset")
        if not self.allowed_strategies:
            raise ValueError("allowed_strategies must not be empty")
        if any(
            not isinstance(strategy, StrategyMode)
            for strategy in self.allowed_strategies
        ):
            raise TypeError("allowed_strategies must contain StrategyMode values")
        _require_string_set("allowed_tools", self.allowed_tools, allow_empty=True)
        _require_string_set(
            "knowledge_scopes",
            self.knowledge_scopes,
            allow_empty=True,
        )
        _require_string_set("permissions", self.permissions, allow_empty=True)
        if not isinstance(self.budget, ExecutionBudget):
            raise TypeError("budget must be an ExecutionBudget")
        _require_string_set(
            "termination_conditions",
            self.termination_conditions,
            allow_empty=False,
        )
```

`__post_init__` 必须验证：稳定 ID 非空且只允许小写字母、数字、点、下划线和短横线；语义版本合法；负责人、所有 Schema/Policy/Prompt ID 非空；`capability_ids`、`supported_task_types`、`allowed_strategies` 和 `termination_conditions` 非空；集合元素全部为非空字符串；`kind` 和策略元素类型正确。`CapabilityRequirement` 的 `all_of` 与 `any_of` 不能同时为空。

在 `core/ports.py` 导入 `AgentSpec` 并将 `AgentPlugin` 扩展为：

```python
@runtime_checkable
class AgentPlugin(Protocol):
    """未来 Specialist Agent 或 Agent 子图的稳定扩展端口。"""

    descriptor: ExtensionDescriptor
    spec: AgentSpec

    async def run(self, task: SupervisorTask) -> RunResult:
        """只执行 Supervisor 分配且已裁剪上下文的子任务。"""
        pass
```

保留 `descriptor` 以兼容现有扩展契约，后续 Validator 校验它与 `spec` 一致。

- [ ] **Step 5: 运行目标测试并确认通过**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_spec tests.architecture.test_core_contracts -v
```

Expected: PASS，且既有核心契约测试无回归。

- [ ] **Step 6: 保存任务评审证据**

记录本任务文件清单、失败原因、通过测试数量和命令输出摘要；不得记录 Git 提交或声称后续 Validator 已完成。

