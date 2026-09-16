# S1 Task 4：Agent Factory 装配边界报告

## 实际变更文件

- `src/efficiency_platform_agent/agents/factory.py`
  - 新增 `AgentFactory`，依赖显式 `AgentRegistry` 和 `AgentValidator`。
  - `create()` 固定执行：Registry 查找 → Builder 调用 → Validator 实例校验 → 返回实例。
  - Registry 查找位于异常归一化范围之外，因此未知 ID 的 `AgentNotFoundError` 原样保留。
  - Builder 异常归一化为不包含原始详情的 `AgentAssemblyError`，并通过异常链保留原异常。
  - Validator 抛出的 `AgentDefinitionError`（包括非法实例和契约不匹配）归一化为安全的 `AgentAssemblyError`，并保留异常链。
- `tests/unit/agents/test_agent_factory.py`
  - 覆盖合法创建、未知 ID、Builder 异常、非 `AgentPlugin` 返回值、实例 Spec 不匹配和调用顺序。

## TDD 证据

### RED

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_factory -v
```

结果：失败（`ModuleNotFoundError: No module named 'efficiency_platform_agent.agents.factory'`），证明测试先于生产实现运行。

### GREEN

命令：

```powershell
uv run python -m unittest tests.unit.agents.test_agent_factory tests.unit.agents.test_agent_registry tests.unit.agents.test_agent_validation -v
```

结果：21 项全部通过。

全量回归命令：

```powershell
uv run python -m unittest discover -s tests -v
```

结果：74 项中 73 项通过，1 项失败。失败为既有 `config.test_llm_configuration_template.LlmConfigurationTemplateTest.test_local_env_deepseek_public_state_matches_when_present`，原因是本机 `.env` 的 DeepSeek 公开状态不匹配；本次未修改配置文件，也未连接外部服务。

## 失败矩阵与安全性自检

| 场景 | Factory 行为 | 详情泄露 | 异常链 |
| --- | --- | --- | --- |
| 未注册 ID | 原样抛 `AgentNotFoundError` | 不新增消息 | Registry 原链保留 |
| Builder 抛异常 | 抛 `AgentAssemblyError("Agent 装配失败: <id>")` | 不包含原异常文本 | `__cause__` 保留 |
| Builder 返回非 Plugin | Validator 失败后抛 `AgentAssemblyError` | 不包含类型/内部文本 | `__cause__` 保留 |
| 实例 Spec 不一致 | Validator 失败后抛 `AgentAssemblyError` | 不包含实例差异详情 | `__cause__` 保留 |
| 合法实例 | 返回 Builder 原实例 | 无 | 不适用 |

自检结论：没有新增 DI 容器、Graph 编译、Provider 装配、外部服务调用、密钥或配置写入；Factory 只消费既有三项边界并返回 `AgentPlugin`。

## 顾虑

当前归一化按既有 Validator 契约捕获 `AgentDefinitionError`。若未来 Validator 改为抛出其他异常类型，应先明确是否也纳入装配层安全归一化，避免在未批准前扩大异常吞噬范围。
