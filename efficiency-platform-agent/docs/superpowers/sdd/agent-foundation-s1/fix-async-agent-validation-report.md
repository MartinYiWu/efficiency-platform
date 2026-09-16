# S1 异步 Agent 校验修复报告

## 状态

已完成 S1 终审 Important #1 修复。`AgentValidator` 现在在运行时协议的同名属性检查之后，显式拒绝不可调用的 `run` 以及同步 `run`；`AgentFactory` 保持既有的 `AgentDefinitionError` 至 `AgentAssemblyError` 归一化边界。

## 变更范围

- `src/efficiency_platform_agent/agents/validation.py`
  - 使用 `inspect.iscoroutinefunction` 校验 `run` 是协程函数。
  - 先校验 `run` 可调用，再校验异步性；不满足时抛出 `AgentInstanceMismatchError`，保持失败关闭。
- `tests/unit/agents/test_agent_validation.py`
  - 覆盖 `run=1` 和同步函数两种运行时协议误放行情形。
- `tests/unit/agents/test_agent_factory.py`
  - 覆盖上述两种非法实例经 Factory 后均归一化为 `AgentAssemblyError`，且保留 `AgentInstanceMismatchError` 作为原因。

未修改 Registry、Factory 实现、配置、真实 `.env` 或其他业务文件。

## TDD 证据

### RED

先新增四项负向断言后执行：

```powershell
\.venv\Scripts\python.exe -m unittest tests.unit.agents.test_agent_validation tests.unit.agents.test_agent_factory -v
```

结果：`Ran 17 tests`，其中 4 项失败：Validator 对不可调用和同步 `run` 均未抛错，Factory 因此也未归一化为 `AgentAssemblyError`。失败原因与本次缺口一致。

### GREEN

在 Validator 增加最小的可调用与协程函数校验后，使用相同命令复测：

```text
Ran 17 tests in 0.007s
OK
```

## 回归验证

执行：

```powershell
\.venv\Scripts\python.exe -m unittest tests.unit.agents.test_agent_validation tests.unit.agents.test_agent_factory tests.architecture.test_core_contracts tests.architecture.test_dependency_rules -v
\.venv\Scripts\python.exe -m compileall -q src\efficiency_platform_agent\agents\validation.py tests\unit\agents\test_agent_validation.py tests\unit\agents\test_agent_factory.py
```

结果：单元、契约与 AST 依赖守卫共 `Ran 42 tests in 0.636s`，全部通过；源码编译命令无输出且退出码为 0。

## 未验证项

未运行完整仓库回归、外部运行时或基础设施验证；本修复不涉及这些范围。
