# Task 6 文档交付报告

## 文件

- `docs/architecture/扩展开发约定.md`
- `docs/standards/06-Agent-Prompt-Tool开发规范.md`
- `docs/superpowers/sdd/agent-foundation-s1/task-6-docs-report.md`

## 变更点

- 两份规范均新增新 Agent 的确定接入顺序：定义 `AgentSpec`、定义稳定输入输出 Schema、实现 `AgentPlugin`、`AgentValidator` 本地校验、`AgentRegistry` 显式注册、`AgentFactory` 装配、运行准入契约测试，最后才由 Supervisor 按能力匹配。
- 明确 `AgentSpec` 的完整表达范围，并补充 `CapabilityRequirement`、`AgentValidator`、`AgentRegistry`、`AgentFactory` 的职责和失败关闭要求。
- 明确禁止修改 Harness/Graph Runtime 公共生命周期、直接调用 Provider SDK、动态扫描或动态导入、通过 `__init__.py` 导入副作用注册，以及绕过校验/注册/装配链路。
- 明确 S1 文档不代表真实 LangGraph、Provider、网络、数据库或其他外部运行时已经接入。

## 对 Task 6 门禁的对应

- 已覆盖 brief Step 3 的接入顺序、中文契约说明和全部注册禁止项。
- 已覆盖 S1 门禁 1～6 的文档化要求：AgentSpec 完整性、Validator 失败关闭、显式 Registry、Factory 安全装配，以及不改变公共运行时语义。
- 文档新增内容均使用中文；标识符和标准技术术语保留原名。

## 未验证项

- 本工作包未运行测试、compileall 或敏感信息扫描；这些验证由主任务统一执行。
- 未修改计划、进度账本、治理测试、架构测试或任何生产代码，因此不对其当前状态作完成声明。
- 真实模型、网络、数据库、Redis、COS、Provider、LangGraph、Harness 及 Windows/Linux 生产兼容性仍未验证。
