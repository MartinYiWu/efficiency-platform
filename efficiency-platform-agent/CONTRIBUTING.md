# 贡献指南

本仓库只接受符合纯 Agent 侧边界的变更。所有贡献者 MUST 使用本文的流程；规则冲突时 MUST 以 `AGENTS.md` 为根规则入口。

## 开始前检查

开始前 MUST 确认需求范围、相关目录、现有改动与文件所有权，阅读 `AGENTS.md`、`Agent.md`、相关架构文档和现有实现。MUST NOT 顺带修改 Java 侧、部署拓扑或无关文件；范围、风险或授权不清时 SHOULD 先澄清。

## 需求分类

需求 MUST 分类为：缺陷修复、既有能力扩展、新 Agent/Strategy/Workflow/Tool/Provider/Prompt/Capability、架构变更、数据或 SQL 变更、文档治理或安全加固。分类决定测试与设计深度；任何引入业务 Agent、第二 Graph Runtime 或未批准技术组件的需求 MUST 先停止并走 ADR。

## 设计与 ADR 触发条件

跨层依赖、运行状态/事件契约变更、策略选择语义、持久化边界、Tool 权限、Provider 能力、模型/向量版本、公开数据来源或安全策略变更 MUST 先形成设计或 ADR。ADR MUST 记录候选方案、裁决、风险、补偿措施、责任人及复审条件；已批准裁决 MUST NOT 被静默覆盖。

## 实施计划

中等及以上改动 MUST 先写实施计划，包含范围、非目标、前置条件、文件清单、分步验证、数据变更、回滚、风险和完成定义。计划 SHOULD 将每项新增代码映射到所有者、契约、测试和文档；紧急小修 MAY 使用简短计划，但仍 MUST 写明验证。

## 测试先行与最小实现

流程固定为：**确认范围 → 阅读规范/实现 → 设计或 ADR → 实施计划 → 测试先行 → 最小实现 → 验证 → 文档同步 → 评审交付**。新增或修复行为 MUST 先出现可正确失败的测试，再实现最小改动；MUST NOT 用未覆盖的重构代替验证。新端口、Provider、Tool、Strategy、Agent、RAG/OCR 能力分别 SHOULD 覆盖其契约、权限、超时、失败恢复、上下文隔离或质量回归边界。

## 文件范围与依赖

变更 MUST 保持文件范围最小且可追溯。`core` 只依赖自身和标准库；`contracts` MUST NOT 依赖 API、Harness、编排或策略；内部层 MUST NOT 依赖 `api`；`providers` 与 `persistence` MUST NOT 反向依赖执行层。厂商 SDK MUST 留在 Provider，Tool MUST 经 `tools/runtime`，专家 Agent MUST 经 Supervisor 协作。

## 验证矩阵

当前工程可执行的基础验证是：

| 验证 | 当前命令 | 适用条件 |
|---|---|---|
| 项目测试 | `uv run pytest -m "not real_external" -q` | 每次相关变更 MUST 执行 |
| 标准库测试 | `uv run python -m unittest discover -s tests -p "test_*.py" -q` | 每次相关变更 MUST 执行 |
| 源码编译 | `uv run python -m compileall -q src tests scripts` | Python 源码变更 MUST 执行 |
| AST 架构守卫 | `uv run python -m unittest tests.architecture.test_dependency_rules -v` | 新增或修改模块依赖 MUST 执行 |
| 静态质量 | `uv run ruff check src tests scripts`、`uv run mypy src/efficiency_platform_agent` | Python 源码变更 MUST 执行 |

依赖扫描与安全扫描仍需按对应阶段计划执行并单独记录；当前项目已经锁定并使用 pytest、pytest-asyncio、Ruff 和 mypy，不能再将它们描述为“尚未安装”。

## 评审清单

评审者 MUST 检查：范围和 ADR 是否一致；测试是否先失败且覆盖新行为；依赖方向、Provider 与 Tool Runtime 是否未被绕过；租户、权限、SSRF、Prompt Injection、日志脱敏和模型输出校验是否适用；SQL 是否具备预检、授权、验证和回滚；文档是否同步且无无解释占位。SHOULD 检查超时、取消、幂等、预算、审计、错误映射和可观测字段。

## 交付状态

交付 MUST 区分“已实现”“已验证”“未验证”“待确认”“阻塞”。完成声明 MUST 附带本次执行的命令、结果及未覆盖范围；MUST NOT 用历史结果或未安装工具替代新鲜验证证据。

## Git 与无 Git 场景

Git 仓库中，MUST 查看目标分支和工作区改动，SHOULD 使用文件白名单暂存，MUST NOT 混入他人无关改动；提交信息 SHOULD 说明范围与验证。无 Git 场景中，MUST 输出变更文件清单、版本/时间、验证命令与结果、已知风险和回滚方式；MUST NOT 假称已提交、已合并或已推送。
