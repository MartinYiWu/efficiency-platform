# 最终审查集中修复简报

## 1. 目标

关闭最终全项目审查发现的 5 个 Important 和 1 个 Minor。必须遵循测试先行：先新增能够复现缺口的失败测试并记录 RED，再修改实现/文档使其通过。

保持以下边界：纯 Agent 侧；不接入真实 LangGraph、LLM、数据库、OCR、Provider；不设计 Java 或部署；不创建具体业务 Agent；不执行数据库或外部写操作；不把骨架描述为已运行接入。

## 2. 允许修改范围

为完成修复可修改：

- `src/efficiency_platform_agent/core/architecture.py`
- `src/efficiency_platform_agent/core/enums.py`
- `src/efficiency_platform_agent/core/run.py`
- `src/efficiency_platform_agent/core/ports.py`
- `tests/architecture/*.py`
- `tests/governance/test_documentation_contract.py`
- `README.md`、`AGENTS.md`、`Agent.md`、`CONTRIBUTING.md`、`SECURITY.md`
- `sql/README.md`
- `docs/architecture/*.md`
- `docs/standards/*.md`
- `docs/templates/*.md`
- `docs/superpowers/specs/*.md`
- `docs/superpowers/plans/*.md`（允许将旧英文主题计划重命名为合规中文主题，并更新全部引用）
- `docs/superpowers/sdd/progress.md`
- 新建 `docs/superpowers/sdd/final-review-fix-report.md`

不得修改既有 Task 1–7 的 brief/report 历史证据；除旧计划的合规重命名外，不删除历史文档。

## 3. 修复 A：依赖守卫封闭（Important）

先新增失败测试，至少复现：

- `from efficiency_platform_agent import api` 被 core 拒绝；
- `from efficiency_platform_agent import strategies` 被 providers 拒绝；
- 相对导入和 `__init__.py` 重导出不能绕过；
- `capabilities -> strategies` 被拒绝；
- `tools -> orchestration` 被拒绝；
- contracts、core、context、memory、persistence、providers、capabilities、tools、execution layers 的典型允许/禁止方向。

实现要求：

- `ImportFrom` 必须展开 `node.names`，根包导入解析为具体内部模块；星号导入默认失败关闭或有等价安全处理。
- 使用显式层级允许矩阵或等价完整规则，不能只靠零散特例。
- 核心/基础契约层不得依赖上层执行或入口；capabilities/tools/providers/persistence 不得反向依赖 routing/orchestration/strategies/agents/workflows/harness/api。
- API 可作为组合入口依赖下层；执行层之间仅保留架构文档明确允许的方向。
- 未知顶层包必须失败关闭或明确分类，不能静默漏检。
- 同步 `02-架构与依赖规范.md`，使文档矩阵与代码完全一致。

## 4. 修复 B：治理契约测试真实化（Important）

将临时扫描固化为自动化测试，至少覆盖：

- 所有治理 Markdown 的相对链接真实存在；忽略外部 URL、锚点和 fenced code 示例。
- 00–09 规范与正式架构/技术选型/扩展约定拥有要求的元数据和合法状态；模板默认草案。
- 必需章节和五类文档命名/状态/六项例外关键规则存在。
- 治理正文不存在未解释占位；合法示例应通过显式允许清单而不是粗暴忽略整份文件。
- 项目内 Java 文件数为 0；具体业务 Agent 目录为 0；第三方 Graph Runtime 导入为 0（当前骨架），并防止第二运行时。
- Tool/Provider 边界由依赖负例与端口契约字段测试证明，不得继续仅用空包可导入作为“边界通过”证据。

测试可新增辅助函数，但保持标准库实现。测试数量增加后，后续报告使用实际数量，不再硬编码 15。

## 5. 修复 C：权威文档元数据与命名（Important）

- 为正式架构文档 `纯Agent侧总体架构.md`、`Agent侧技术组件选型.md`、`扩展开发约定.md` 补齐标题、状态、作者/负责人、创建/更新时间、评审/批准、关联文档、替代关系、适用范围。
- 用户已经明确确认架构骨架，但没有给出实名批准人。不得虚构实名或批准证据：可将架构/选型状态记为 `评审中`，并把“最终裁决/确定”改成“当前基线/候选基线”；如果保留已批准，必须引用可审计的明确用户确认记录，本地目前没有该记录时不得保留。
- 为 00–05 规范补齐与 06–09 相同的完整元数据，状态保持 `评审中`。
- 修正 `01` 中把整个 `docs/architecture/` 说成“已批准”的表述，改为按文档元数据判定。
- 检查规范体系设计文档：若现有 `已批准` 没有本地批准证据，降为 `评审中` 并修正计划/brief中把它称为已批准的当前性表述；历史报告可保留当时原话但不作为当前批准证据。
- 将 `docs/superpowers/plans/2026-09-01-agent-architecture-scaffold.md` 重命名为符合规范的中文主题实施计划，例如 `2026-09-01-Agent侧架构骨架-实施计划.md`，更新所有真实链接/引用；若无法安全重命名，则在 00 索引记录完整六项命名例外。优先重命名。
- `AGENTS.md` 优先级规则仍可保留“已批准 ADR/架构设计”，但所有当前文档状态必须可审计；不得把自动测试通过等同批准。

## 6. 修复 D：Alembic verify_only 语义闭合（Important）

统一 `05`、`sql/README.md`、SQL 模板：

- `verify_only` 只允许 Alembic 外部纯只读验证，绝不运行 `alembic upgrade/downgrade/stamp/current` 中会写版本表的操作，绝不推进 revision，绝不写权威账本。
- 任何会更新 Alembic 版本表或权威账本的操作都属于数据库写入，必须选择 `alembic_embedded` 或 `external_controlled`，走明确授权、原子执行权、状态机、对账和失败恢复。
- 给出允许/拒绝示例，避免把“校验 revision”误读为执行 revision。

增加治理契约断言关键语义，防止回退。

## 7. 修复 E：Core 端口从宽泛占位变为版本化治理契约（Important）

不接真实运行时，但在 Core 提供框架中立、冻结且版本化的最小契约：

- 受控 JSON 值类型，稳定边界中不再使用 `Any`。
- `ExecutionBudget`：最大循环、工具调用、Token、耗时、费用等非负/正值校验。
- `ExtensionDescriptor`：名称、语义版本、输入/输出 Schema 版本、权限、预算、终止条件、Checkpoint 版本。
- `SupervisorTask`：子任务 ID、父 Run、目标 Agent、裁剪后的 JSON 输入/上下文视图、允许工具、预算；AgentPlugin 接收它而非完整用户 RunRequest/RunContext。
- Tool 请求/结果：版本、结构化参数/输出、超时、审批绑定、副作用/幂等标记、结构化错误和输出限制。
- Provider 请求/结果：版本化消息/options、结构化 usage、错误归一化，不返回厂商对象。
- 所有 dataclass 使用 `frozen=True, slots=True`；集合优先不可变；字段校验失败关闭。
- Protocol 暴露 descriptor，并使用上述结构化请求/结果；保持框架和厂商中立。

先写字段、无 `Any`、不可变、非法值拒绝、Agent 子任务裁剪、Tool/Provider 结果结构的失败测试。同步 03/06 文档，使“当前端口稳定/受治理”与实现相符。

## 8. 修复 F：Run 状态合法转换（Minor）

- 在 Core 增加框架中立的不可变合法转换表和校验函数/方法。
- 定义 CREATED、QUEUED、RUNNING、三类 WAITING、四个终态之间的合法路径；终态不可逆。
- 覆盖等待恢复、取消、超时、失败、重复同状态事件（明确允许幂等或拒绝）、非法跳转测试。
- 同步 `Agent.md` 状态说明。

## 9. 验证与报告

至少记录：

1. RED：新增测试在修复实现前的失败名称和原因；
2. `python --version`；
3. `python -m unittest discover -s tests -v` 的实际 ran/passed/failures/errors/skipped；
4. 50 个或当前实际数量源码文件的内存 `compile()`；
5. 依赖守卫对全部新增绕过样例的结果；
6. Markdown 相对链接、元数据、占位、Java、具体业务 Agent、第三方 Graph Runtime 的自动测试结果；
7. 未执行数据库、部署、Java、Git、外部服务写操作；当前目录非 Git 仓库。

报告必须区分：骨架/契约已建立、测试已通过、真实运行时/Provider/DB/OCR 未接入、文档仍处于评审中且尚未正式批准。
