### Task 2: 建立失败关闭的 Agent Validator

**Files:**
- Create: `src/efficiency_platform_agent/agents/errors.py`
- Create: `src/efficiency_platform_agent/agents/validation.py`
- Create: `tests/support/__init__.py`
- Create: `tests/support/agent_fakes.py`
- Create: `tests/unit/agents/test_agent_validation.py`

**Interfaces:**
- Consumes: `AgentSpec`、`AgentPlugin`、`ExtensionDescriptor`。
- Produces: `AgentDefinitionError`、`AgentInstanceMismatchError`、`AgentValidator.validate_spec()`、`AgentValidator.validate_instance()`。

- [ ] **Step 1: 建立后续任务共用的合成 Agent 工厂**

创建空的 `tests/support/__init__.py`，并在 `tests/support/agent_fakes.py` 写入：

```python
from __future__ import annotations

from dataclasses import dataclass

from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.enums import AgentKind, RunStatus, StrategyMode
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    ExtensionDescriptor,
    JsonObject,
    RunResult,
    SupervisorTask,
)


def build_synthetic_spec(
    agent_id: str = "synthetic_research_agent",
    capability_ids: frozenset[str] = frozenset({"public_research"}),
) -> AgentSpec:
    """构造不包含真实业务和外部配置的合成 Agent 定义。"""

    return AgentSpec(
        agent_id=agent_id,
        semantic_version="1.0.0",
        owner="agent_platform",
        kind=AgentKind.SPECIALIST,
        capability_ids=capability_ids,
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
        budget=ExecutionBudget(
            max_iterations=3,
            max_tool_calls=2,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            timeout_ms=30_000,
            max_cost_microunits=0,
        ),
        termination_conditions=frozenset({"succeeded", "failed"}),
    )


@dataclass(slots=True)
class SyntheticAgent:
    """只用于离线契约测试的合成 Specialist。"""

    descriptor: ExtensionDescriptor
    spec: AgentSpec

    async def run(self, task: SupervisorTask) -> RunResult:
        """返回不访问任何外部系统的确定性合成结果。"""

        return RunResult(
            run_id=task.parent_run_id,
            status=RunStatus.SUCCEEDED,
            strategy=StrategyMode.MULTI_AGENT,
            output=JsonObject((("task_id", task.task_id),)),
        )


def build_synthetic_agent(
    spec: AgentSpec | None = None,
    *,
    descriptor_name: str | None = None,
) -> SyntheticAgent:
    """按 AgentSpec 构造可测试实例，并允许显式制造名称不一致。"""

    resolved_spec = spec or build_synthetic_spec()
    descriptor = ExtensionDescriptor(
        name=descriptor_name or resolved_spec.agent_id,
        semantic_version=resolved_spec.semantic_version,
        input_schema_version=resolved_spec.input_schema_version,
        output_schema_version=resolved_spec.output_schema_version,
        permissions=resolved_spec.permissions,
        budget=resolved_spec.budget,
        termination_conditions=resolved_spec.termination_conditions,
        checkpoint_version=resolved_spec.checkpoint_version,
    )
    return SyntheticAgent(descriptor=descriptor, spec=resolved_spec)
```

- [ ] **Step 2: 编写 Validator 失败测试**

测试必须覆盖：合法 Spec 无问题；缺失能力、Schema、策略和终止条件被核心契约拒绝；Plugin 的 `descriptor.name`、版本、Schema、权限、Checkpoint 与 Spec 不一致时拒绝；Plugin 不满足 `AgentPlugin` 时拒绝。测试入口：

```python
from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.errors import AgentInstanceMismatchError
from efficiency_platform_agent.agents.validation import AgentValidator
from tests.support.agent_fakes import build_synthetic_agent


class AgentValidationTest(unittest.TestCase):
    def test_validate_instance_rejects_descriptor_spec_mismatch(self) -> None:
        validator = AgentValidator()
        plugin = build_synthetic_agent(descriptor_name="different_agent")

        with self.assertRaises(AgentInstanceMismatchError) as caught:
            validator.validate_instance(plugin.spec, plugin)

        self.assertIn("agent_id", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 运行测试并确认失败**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation -v
```

Expected: FAIL，指出 `agents.validation` 或错误类型不存在。

- [ ] **Step 4: 实现错误类型**

`agents/errors.py` 必须包含：

```python
class AgentDefinitionError(ValueError):
    """Agent 定义缺失、冲突或不满足治理约束。"""


class AgentInstanceMismatchError(AgentDefinitionError):
    """运行实例公开的契约与注册定义不一致。"""


class AgentRegistrationConflictError(AgentDefinitionError):
    """同一 Agent ID 被重复或冲突注册。"""


class AgentNotFoundError(LookupError):
    """Registry 中不存在请求的 Agent 或能力。"""


class AgentAssemblyError(RuntimeError):
    """Agent Builder 失败或返回非法实例。"""
```

- [ ] **Step 5: 实现 AgentValidator**

`AgentValidator` 提供精确接口：

```python
from __future__ import annotations

from efficiency_platform_agent.core.agent import AgentSpec
from efficiency_platform_agent.core.ports import AgentPlugin

from .errors import AgentDefinitionError, AgentInstanceMismatchError


class AgentValidator:
    """在注册和装配边界执行失败关闭的 Agent 契约校验。"""

    def validate_spec(self, spec: AgentSpec) -> None:
        if not isinstance(spec, AgentSpec):
            raise AgentDefinitionError("Agent 定义必须是 AgentSpec")

    def validate_instance(self, spec: AgentSpec, plugin: AgentPlugin) -> None:
        self.validate_spec(spec)
        if not isinstance(plugin, AgentPlugin):
            raise AgentInstanceMismatchError("Agent 实例不满足 AgentPlugin 契约")
        if plugin.spec != spec:
            raise AgentInstanceMismatchError("Agent 实例的 spec 与注册定义不一致")

        descriptor = plugin.descriptor
        comparisons = (
            ("agent_id", descriptor.name, spec.agent_id),
            ("semantic_version", descriptor.semantic_version, spec.semantic_version),
            (
                "input_schema_version",
                descriptor.input_schema_version,
                spec.input_schema_version,
            ),
            (
                "output_schema_version",
                descriptor.output_schema_version,
                spec.output_schema_version,
            ),
            ("permissions", descriptor.permissions, spec.permissions),
            ("budget", descriptor.budget, spec.budget),
            (
                "termination_conditions",
                descriptor.termination_conditions,
                spec.termination_conditions,
            ),
            (
                "checkpoint_version",
                descriptor.checkpoint_version,
                spec.checkpoint_version,
            ),
        )
        mismatches = tuple(
            field_name
            for field_name, actual, expected in comparisons
            if actual != expected
        )
        if mismatches:
            fields = ", ".join(mismatches)
            raise AgentInstanceMismatchError(
                f"Agent 实例与注册定义不一致: {fields}"
            )
```

`validate_spec` 验证对象类型及跨字段约束。`validate_instance` 先执行 Spec 校验，再验证运行时 Protocol，并逐项比较：

```text
descriptor.name                 == spec.agent_id
descriptor.semantic_version     == spec.semantic_version
descriptor.input_schema_version == spec.input_schema_version
descriptor.output_schema_version == spec.output_schema_version
descriptor.permissions          == spec.permissions
descriptor.checkpoint_version   == spec.checkpoint_version
descriptor.termination_conditions == spec.termination_conditions
```

Validator 还必须校验 `descriptor.budget == spec.budget`，确保 AgentSpec 与运行实例对预算只有一个一致语义。

- [ ] **Step 6: 运行 Validator 测试和架构守卫**

Run:

```powershell
uv run python -m unittest tests.unit.agents.test_agent_validation tests.architecture.test_dependency_rules -v
```

Expected: PASS；`agents -> core` 合法，`core` 未反向依赖 `agents`。

- [ ] **Step 7: 保存任务评审证据**

记录校验矩阵和通过测试；确认错误消息不包含完整 Prompt、输入正文或 Secret。

