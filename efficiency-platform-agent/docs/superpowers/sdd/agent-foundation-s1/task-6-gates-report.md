# Task 6 架构与文档门禁报告

## 状态

已完成本工作包：仅新增治理与架构门禁测试，未修改文档、生产代码、计划或账本。

## 修改文件

- `tests/governance/test_documentation_contract.py`
  - 要求扩展开发约定记录 `AgentSpec`、`AgentValidator`、`AgentRegistry`、`AgentFactory`、`CapabilityRequirement`、显式注册，以及动态导入/导入副作用注册禁项。
- `tests/architecture/test_core_contracts.py`
  - 静态解析 `core/agent.py`，拒绝对 `agents`、Provider、Harness、LangGraph 及其实现模块的依赖。

## RED

执行：

```powershell
uv run python -m unittest tests.governance.test_documentation_contract tests.architecture.test_core_contracts tests.architecture.test_dependency_rules -v
```

结果：40 项测试中 3 项失败。新增文档门禁最初因禁项文案未使用精确短语而失败；组合命令另有 1 项既有治理链接检查失败，指向 `task-6-docs-baseline` 下的文档快照相对链接，非本工作包修改范围。

## GREEN

执行：

```powershell
uv run python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_extension_convention_documents_stable_s1_entry_points_and_registration_prohibitions tests.architecture.test_core_contracts.CoreContractsTest.test_core_agent_does_not_depend_on_agent_runtime_implementations -v
```

结果：2 项通过，0 失败，0 错误。

## 顾虑

- 未执行完整离线回归或编译；本工作包只验证新增两项门禁。
- 组合门禁仍受 `task-6-docs-baseline` 文档快照链接失败影响，需要由该快照/文档责任方处理后再运行完整命令。
