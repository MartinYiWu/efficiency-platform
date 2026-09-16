# Task 2 落地报告：根目录强制规则与 Agent 总纲

## 状态

已完成 Task 2 指定的四份根目录治理文档；未执行 Git 操作，未创建 Brief 外的实现文件。完整治理测试仍为 RED，原因仅为后续任务尚未创建的 SQL、详细规范和模板文档。

## 实现

- `AGENTS.md`：建立纯 Agent 侧边界、规则优先级、单一 Graph Runtime、Supervisor、Provider、Tool Runtime、共享 DDL 授权、Secret、完成证据和详细规范入口等强制规则。
- `Agent.md`：固化 Harnessed Hybrid Multi-Agent Architecture、五种执行策略、Strategy Router 与 Supervisor 的职责边界、Specialist Subgraph 约束、运行状态、核心层与扩展准入规则。
- `CONTRIBUTING.md`：建立需求分类、设计/ADR、实施计划、TDD、最小文件范围、验证矩阵、评审、交付状态以及 Git/无 Git 交付规则；明确 `unittest`、源码编译和 AST 守卫当前可执行，pytest、Ruff、mypy 和扫描属于组件引入后目标。
- `SECURITY.md`：建立项目负责人报告路径、Secret、租户隔离、Prompt Injection、Tool、SSRF、文件、SQL、日志、模型输出、依赖与安全验收基线；内容审核暂不建设不构成基础安全豁免。

## 测试命令与结果

1. `python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_agents_rules_link_to_detailed_standards tests.governance.test_documentation_contract.DocumentationContractTest.test_agent_handbook_preserves_selected_architecture -v`
   - 结果：退出码 `0`，2/2 通过。
2. `python -m unittest tests.governance.test_documentation_contract -v`
   - 结果：退出码 `1`，已通过 2 项根文档契约；其余 RED 仅由 16 个后续文档缺失引起：`sql/README.md`、10 个 `docs/standards/` 文档（`00` 至 `09`）和 5 个 `docs/templates/` 文档。失败不涉及本任务新增的四份根文档。

## 文件清单

- `AGENTS.md`
- `Agent.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `docs/superpowers/sdd/task-2-report.md`

## 自检

- 章节顺序：`AGENTS.md` 的 10 个必需章节与 `Agent.md` 的 11 个必需章节均已逐项顺序校验。
- 结构契约：聚焦测试已覆盖根规则详细规范链接和架构关键词保留。
- 占位：扫描无 `TODO`/`TBD`。
- 重复与冲突：根文档只保留裁决和入口，不复制详细规范全文；与现有总体架构、技术选型、扩展开发约定一致，未引入 Java、部署、第二运行时或专家自由对话规则。
- 冗长度：`AGENTS.md` 保持根规则粒度；细节分别收敛到总纲、贡献和安全文档。

## 关注点

- `AGENTS.md` 和 `Agent.md` 已链接 `docs/standards/00-规范索引.md`，该目标由后续任务创建；因此完整治理测试在当前阶段按预期保持 RED。
- 本次没有安装或执行 pytest、Ruff、mypy、依赖扫描或安全扫描，也没有声称这些工具已可用。

## 评审修订（Important）

- `SECURITY.md` 的 LLM SQL 规则已收紧为：仅允许经 SQLGlot 完整 AST 校验的单条只读 `SELECT`；CTE 内部同样只允许只读查询；显式拒绝 `INSERT`、`UPDATE`、`DELETE`、`MERGE`、任何 DDL、`SELECT INTO`、多语句和数据修改 CTE。只读账号、表列白名单、行数上限和超时要求保持不变。
- 缺失文档统计已更正为：1 个 `sql/README.md`、10 个 `docs/standards/` 文档（`00` 至 `09`）和 5 个 `docs/templates/` 文档，共 16 个。

### 修订验证

1. `python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_agents_rules_link_to_detailed_standards tests.governance.test_documentation_contract.DocumentationContractTest.test_agent_handbook_preserves_selected_architecture -v`
   - 结果：退出码 `0`，2/2 通过。
2. PowerShell 静态文本检查：验证 SQL 完整 AST、单条只读 `SELECT`、只读 CTE、DML/DDL/`SELECT INTO`/多语句/数据修改 CTE 拒绝项、只读账号/白名单/行数/超时，以及报告中的 1+10+5 统计。
   - 结果：退出码 `0`，检查通过；未发现旧的“限制为 SELECT/CTE”笼统许可表述。
