# Task 5 文件级审查包

## 审查输入

- 任务简报：[task-5-brief.md](task-5-brief.md)
- 实现报告：[task-5-report.md](task-5-report.md)
- 依赖基线快照：`task-5-baseline/`
- 修改后快照：`task-5-current/`（在实施完成后生成）

## 预期变更文件

- 新增：`tests/contract/__init__.py`
- 新增：`tests/contract/agents/__init__.py`
- 新增：`tests/contract/agents/test_agent_plugin_contract.py`

## 审查焦点

该任务只建立离线契约准入测试，验证 Registry → Factory → AgentPlugin.run 的结构化输入输出主链；不得接入网络、数据库、缓存、对象存储、模型或业务数据。

本项目永久不使用 Git；审查以任务简报、实施报告、基线和当前快照替代 Git 差异。

实施 Agent 报告新增契约测试 1/1 通过；全量测试 74/75 通过，唯一失败为任务外本机 `.env` DeepSeek 公开状态测试。审查应核验当前新增测试不访问外部服务，也不把该环境失败归于本任务。
