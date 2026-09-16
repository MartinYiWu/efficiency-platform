# Task 5 实施简报：Agent、安全、可观测性和文档治理规范

## 1. 目标

在不引入具体业务 Agent、不设计 Java 端和部署方案的前提下，形成纯 Agent 侧扩展、安全、运行与文档治理的强制规范。

## 2. 唯一允许创建的交付文件

- `docs/standards/06-Agent-Prompt-Tool开发规范.md`
- `docs/standards/07-安全与数据治理规范.md`
- `docs/standards/08-可观测性与运行治理规范.md`
- `docs/standards/09-文档命名与变更治理规范.md`
- `docs/superpowers/sdd/task-5-report.md`（实施报告）

除上述文件外不得修改其他项目文件。

## 3. 通用约束

- 四份规范的状态均为 `评审中`；用户未批准前不得写成 `已批准`。
- 规范等级仅允许 `MUST`、`MUST NOT`、`SHOULD`、`MAY`；规范性中文措辞不得替代这四级。
- 规则必须能够被代码评审、自动测试或运行证据验证，避免口号式表述。
- 仅覆盖 Agent 侧；不得设计 Java 端接口、工程或职责，不得描述部署架构。
- 不创建具体业务 Agent、Workflow 或 Prompt，不实现内容审核能力。
- 与 `AGENTS.md`、`Agent.md`、`SECURITY.md`、已有标准和架构基线冲突时，以范围更严格且不放宽安全基线为准，并在报告中说明。

## 4. `06-Agent-Prompt-Tool开发规范.md`

分别定义以下扩展类型的必填元数据、输入输出 Schema、权限、预算、终止条件、Checkpoint、错误模型和测试门禁：

- Agent Plugin
- Strategy
- Workflow
- Graph Node
- Prompt
- Tool
- MCP
- Provider

必须覆盖：

- Strategy Router 与 Supervisor 的职责边界；专家子图不得彼此自由对话或直接面向用户。
- Tool 只能经 Tool Runtime 调用；Provider 隔离厂商 SDK；MCP 作为外部工具协议接入仍受 Tool Runtime、安全和审计门禁约束。
- 输入输出采用明确 Schema，默认失败关闭；预算至少覆盖循环次数、工具调用次数、Token、时间和费用。
- Prompt 使用语义版本 `MAJOR.MINOR.PATCH`：不兼容输出或变量变化升 MAJOR；兼容能力扩展升 MINOR；文案修正且语义不变升 PATCH。
- Prompt 变更必须有契约测试、回归样例和回滚版本；不得将 Prompt 文本散落在业务代码中。
- Tool 声明副作用等级、幂等性、超时、重试、授权需求和输出上限；高风险 Tool 在执行前审批。
- Provider 切换不能泄漏厂商对象到核心层；错误归一化并保留可观测证据。

## 5. `07-安全与数据治理规范.md`

必须覆盖并给出允许/禁止边界：

- 租户/用户上下文不可由模型自行构造，跨租户默认拒绝，最小权限和授权传播。
- 外部网页、文件、检索片段和 Tool 输出均视为不可信数据；Prompt Injection 不得提升权限或改变系统边界。
- SSRF：协议、域名/IP、DNS 重绑定、私网/链路本地地址、端口、重定向逐跳校验、响应大小和超时。
- 文件：类型签名、扩展名、大小、解压炸弹、路径穿越、恶意内容隔离；不可信文件不得直接执行。
- LLM 生成 SQL：必须完全复用或加严 `SECURITY.md` 与 `05-数据库与SQL规范.md` 的单条只读 SELECT AST 允许清单、锁定/副作用/资源滥用拒绝和默认失败关闭。
- Secret 不入代码、Prompt、日志、Trace、Artifact；配置引用与轮换；泄漏后的失效和审计。
- 结构化模型输出必须 Schema 校验、长度限制和下游编码，不能因模型声称安全而跳过校验。
- Artifact 使用短期签名 URL、租户绑定、最小访问范围和下载审计。
- 数据分级、最少收集、留存、删除、脱敏和审计；日志不得记录原始敏感 Prompt/响应。
- 高风险 Tool 的执行前审批、审批对象绑定、防重放、超时失效和拒绝默认值。
- 明确：当前不建设内容审核能力，但上述输入、数据和工具安全基线全部适用。

## 6. `08-可观测性与运行治理规范.md`

必须定义：

- Trace 层级：请求/Run、策略、Graph/Workflow、Agent、LLM、Tool、RAG/检索、Checkpoint；父子关系和异步传播。
- 稳定 Span 命名规范与公共属性；租户、用户等敏感标识只能使用不可逆或受控标识，并遵守最小化。
- Metric 命名、单位、类型、Label 白名单和基数预算。
- 明确禁止把 `user_id`、原始 Prompt、完整 URL 查询参数作为 Metric Label；禁止把异常正文等无界值作为 Label。
- 结构化日志字段、关联 ID、级别、脱敏和采样；Trace/Log/Audit 的职责区分。
- 审计事件至少覆盖授权、工具执行、数据访问、配置/Prompt/Provider 版本变更、人工介入和安全拒绝。
- Token、模型费用、工具费用、预算占用与结算口径；未知价格不得伪造成本。
- 重试、退避、熔断、降级、取消、Checkpoint 恢复与告警规则；不得因重试重复高风险副作用。
- SLI/SLO、告警阈值来源、告警去重和处置证据；禁止虚构已经配置的监控或告警。

## 7. `09-文档命名与变更治理规范.md`

必须定义并分别给出合法、非法示例：

```text
YYYY-MM-DD-主题-设计.md
YYYY-MM-DD-主题-实施计划.md
ADR-NNNN-短标题.md
YYYY-MM-DD-主题-技术选型.md
YYYY-MM-DD-主题-评审报告.md
```

必须覆盖：

- 四种状态：`草案`、`评审中`、`已批准`、`已废弃`，以及合法状态迁移和批准证据。
- 文档头必填字段：标题、状态、作者/负责人、创建日期、最后更新日期、评审人/批准人、关联 ADR/设计/计划、替代关系、适用范围。
- ADR 触发条件：架构边界、运行时、协议/契约、核心数据模型、安全基线、不可逆或高退出成本组件决策。
- 禁止使用“最终版”“最新版”“new”“final”等不可追溯命名。
- 已批准决策不得原地覆盖；使用新 ADR/新版本替代，保留双向链接和废弃原因。
- 例外记录必须包含六项：例外规则、业务/技术原因、风险评估、补偿措施、责任人、到期时间与复审条件（“到期时间与复审条件”作为同一项）。
- 相对链接、链接有效性、目录索引、归档和废弃文档保留规则。

## 8. 验证与预期

至少执行：

```powershell
python --version
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_standards_index_links_every_standard_and_template -v
python -m unittest discover -s tests -v
```

预期：索引导航测试和全量套件仍可因 Task 6 的四个未创建模板而保持 RED；失败必须只指向缺失模板，不得来自本任务文档、链接、语法或已有架构测试回归。

## 9. 实施报告

`task-5-report.md` 必须记录：

- 精确文件清单与核心规则覆盖；
- 与现有安全、SQL、架构标准的一致性说明；
- Python 版本；
- 每条命令的 ran/passed/failures/errors/skipped；
- 仍然失败的准确原因；
- 未执行数据库、部署、Java、Git 或外部写操作的事实。
