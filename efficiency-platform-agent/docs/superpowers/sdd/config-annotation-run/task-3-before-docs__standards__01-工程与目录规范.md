# 工程与目录规范

| 属性 | 内容 |
|---|---|
| 标题 | 工程与目录规范 |
| 状态 | 评审中 |
| 作者/负责人 | Agent 平台维护者 |
| 创建日期 | 2026-09-01 |
| 最后更新日期 | 2026-09-01 |
| 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
| 关联 ADR/设计/计划 | [纯 Agent 侧总体架构](../architecture/纯Agent侧总体架构.md)、[Agent 侧技术组件选型](../architecture/Agent侧技术组件选型.md)、[Agent 侧工程规范体系实施计划](../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md) |
| 替代关系 | 无 |
| 适用范围 | `efficiency-platform-agent` 纯 Agent 侧源码、测试、文档、SQL、配置与资源 |
| 不适用范围 | Java 侧工程与部署拓扑 |

## 1. 总则

目录 MUST 表达架构所有权，而不是仅按技术名词或开发者习惯分组。新增文件 MUST 有唯一、可解释的归属；找不到归属时 SHOULD 先澄清职责或调整设计，MUST NOT 新建无所有权的收容目录。

本仓库 MUST 仅包含纯 Agent 侧能力。任何 Java 接口、领域、网关、权限、数据架构或部署拓扑设计与实现 MUST NOT 放入本工程。

## 2. 源码根与一级包

所有可发布 Python 源码 MUST 位于 `src/efficiency_platform_agent/`。测试、脚本或文档 MUST NOT 通过修改 `sys.path` 把仓库其他目录伪装为生产包；现有零依赖骨架测试中的显式 `src` 引入属于测试启动适配，组件化后 SHOULD 由项目安装环境替代。

| 一级包 | MUST 承担的唯一职责 | MUST NOT 承担的职责 |
|---|---|---|
| `api` | 纯 Agent 入站协议、Run/Stream/Resume/Input/Cancel/Health 适配，调用内部契约 | 业务编排、Provider 调用、持久化实现或领域规则 |
| `contracts` | 稳定的请求、响应、事件、错误和 Schema 契约 | 依赖 API、Harness、Graph 或具体厂商对象 |
| `harness` | 单次 Run 的身份、权限、幂等、预算、超时、取消、审计、Trace、Checkpoint 与错误映射 | 复制具体策略实现或绕过统一状态生命周期 |
| `routing` | 意图、风险、复杂度、工具、延迟、成本、策略与模型选择 | 执行专家编排；Multi-Agent 专家调度属于 Supervisor |
| `orchestration` | 唯一 LangGraph Runtime、Graph/Node/Edge、Run 状态机、Checkpoint、暂停恢复和事件流 | 引入第二 Graph Runtime 或包含具体业务流程 |
| `strategies` | Direct、Workflow、ReAct、Plan-and-Execute、Multi-Agent 执行策略 | 直接实例化厂商 SDK、跳过 Harness 或 Tool Runtime |
| `agents` | 未来 Specialist Agent 插件及注册槽 | 专家点对点自由调用、直接面向用户或隐藏业务 Workflow |
| `workflows` | 可复用、确定性、强审计的流程定义 | 充当第二运行时或存放无关辅助函数 |
| `context` | 唯一 Context Builder、裁剪、预算、租户/用户/会话/历史/证据装配 | 各 Agent 私自拼接无限上下文或将不可信内容变成控制指令 |
| `memory` | 短期、长期、情景记忆抽象与检索语义 | 充当权威 Run 状态或丢失来源与租户边界 |
| `prompts` | Prompt 模板、稳定 ID、版本、变量 Schema 与渲染 | 将大段 Prompt 散落到 Python 代码或保存 Secret |
| `tools` | Tool 端口实现、内部/外部/MCP 适配与统一 Runtime 治理 | 绕过 Schema、权限、超时、重试、审计和结果治理 |
| `capabilities` | 可复用技术能力，如模型、检索、文档、OCR、研究、分析、引用、产物 | 包含特定业务部门流程判断或直接替代 Agent/Workflow |
| `providers` | LLM、Embedding、Rerank、OCR、存储、数据库、缓存、搜索等厂商适配 | 向上泄露厂商响应、异常、配置键，或依赖执行层 |
| `persistence` | Run、Checkpoint、Memory、Artifact、Prompt Version、Evaluation 等权威持久化适配 | 依赖 Harness、Routing、Orchestration、Strategy、Agent 或 Workflow |
| `tasks` | 异步任务投递、Outbox Dispatcher、Worker 入口及生命周期边界 | 把 Taskiq/Redis Broker 当权威状态或复制 Graph 内部编排 |
| `observability` | Trace、Metric、Log、Audit 的公共埋点和传播 | 记录密钥、完整 Prompt 或原始敏感文档 |
| `evaluation` | 确定性离线评测、固定回归集和指标定义；在线评测后置 | 在生产路径中隐式改变业务结果或调用未授权付费服务 |
| `security` | 输入、Tool、URL、文件、资源、输出和租户安全策略 | 以“内容审核暂未建设”为由省略基础运行安全 |
| `core` | 仅用 Python 标准库表达的稳定领域类型、枚举、状态、端口和架构守卫 | 依赖任何上层包、框架、厂商 SDK 或基础设施实现 |

### 2.1 已定义的二级包

- `strategies/` MUST 只使用 `direct/`、`workflow/`、`react/`、`plan_execute/`、`multi_agent/` 表达当前候选基线的五种策略；新策略 MUST 先完成设计或 ADR。
- `tools/` MUST 使用 `runtime/`、`internal/`、`external/`、`mcp/` 区分治理层和工具来源；无论来源，调用 MUST 经 `tools/runtime`。
- `capabilities/` MAY 使用 `model/`、`retrieval/`、`document/`、`ocr/`、`research/`、`analytics/`、`citation/`、`artifact/`；新增 Capability MUST 证明是可复用技术能力。
- `providers/` MAY 使用 `llm/`、`embedding/`、`rerank/`、`ocr/`、`storage/`、`database/`、`cache/`、`search/`；每类 Provider MUST 对上实现稳定端口。

## 3. 通用代码的真实归属

`common/`、`utils/`、`misc/`、`helpers/` 等无所有权收容层 MUST NOT 新建。已有类似模块在触达时 SHOULD 迁移到真实归属，并以测试保护行为。

| 代码类型 | MUST 归属 |
|---|---|
| 框架中立的枚举、不可变值对象、Protocol、领域错误 | `core/` 或稳定外部契约对应的 `contracts/` |
| 组合多个 Provider 形成的检索、OCR、引用等技术能力 | `capabilities/<type>/` |
| 厂商 SDK、HTTP API、连接对象和错误映射 | `providers/<type>/` |
| Tool Schema、权限、超时、重试、审计、结果限制 | `tools/runtime/` |
| 某个 Tool 的具体实现 | 按来源放入 `tools/internal/`、`tools/external/` 或 `tools/mcp/` |
| Run 生命周期共性治理 | `harness/`；MUST NOT 放入 Strategy 或 Agent |
| 结构化日志、Trace、Metric、Audit 公共实现 | `observability/` |
| 输入、URL、文件、SQL 与资源访问策略 | `security/` |

“被两个模块使用”不足以定义通用层。提取共享代码前 MUST 说明它代表的稳定概念、依赖方向和负责人。

## 4. 测试目录

测试 MUST 位于 `tests/`，目录 SHOULD 与测试目的而非实现细节对应：

```text
tests/
├─ unit/             # 单一模块或纯函数，不访问真实外部系统
├─ contract/         # 稳定端口、Schema、事件、Provider/Tool 适配器契约
├─ architecture/     # 包结构、依赖方向、枚举与扩展槽守卫
├─ governance/       # 文档、命名、安全红线和治理产物契约
├─ graph/            # Node、状态迁移、暂停/恢复、Checkpoint、终止与重放
├─ integration/      # Provider、数据库、缓存、HTTP 等受控集成
├─ security/         # 租户隔离、权限、Prompt Injection、SSRF、文件和 SQL 安全
├─ evaluation/       # RAG/OCR/模型固定数据集及质量回归
└─ acceptance/       # 从入站契约到结果、事件、引用、产物的端到端验收
```

- 当前骨架的 `tests/architecture` 与 `tests/governance` MUST 保持零第三方依赖可执行。
- 单元测试文件 MUST 命名为 `test_<被测主题>.py`；测试类 SHOULD 命名为 `<Subject>Test`，测试函数 MUST 以 `test_` 开头并表达行为。
- 契约和集成测试所需样本 SHOULD 放入相邻 `fixtures/` 或 `tests/fixtures/<domain>/`，MUST 使用合成或脱敏数据。
- 测试产物、缓存和下载文件 MUST 写入临时目录，MUST NOT 污染源码或固定依赖开发者机器路径。
- 测试分层的执行与证据要求以[测试与质量门禁](04-测试与质量门禁.md)为准。

## 5. 文档目录

| 目录 | MUST 管理的内容 |
|---|---|
| `docs/architecture/` | 总体架构、技术选型、扩展约定和架构专题；每份文档的批准状态 MUST 按其元数据和可审计证据判定，目录本身不表示已批准 |
| `docs/standards/` | 分领域可执行规则和规范索引；MUST 避免复制根规则全文 |
| `docs/templates/` | 可复用的架构、ADR、选型、计划和 SQL 模板；模板 MUST NOT 被当作已完成产物 |
| `docs/superpowers/specs/` | 设计输入与边界；当前状态 MUST 以文档元数据为准 |
| `docs/superpowers/plans/` | 设计对应的实施计划和逐步验证；计划存在不等于设计已批准 |
| `docs/superpowers/sdd/` | 分任务 brief、进展和实施报告等协调产物 |

正式文档 MUST 使用稳定中文主题命名并包含状态、负责人、适用范围、更新时间和关联决策。草稿和任务报告 MAY 使用任务约定的固定路径，但 MUST NOT 伪装为已批准架构裁决。

## 6. SQL 目录

SQL MUST 只定义 Agent 独立命名空间中的受治理变更，MUST NOT 与 Java 表混写。每个变更包 MUST 位于 `sql/changes/`：

```text
sql/
├─ README.md
└─ changes/
   └─ YYYYMMDD_NNN_中文主题/
      ├─ 00-变更说明.md
      ├─ 01-precheck.sql
      ├─ 02-up.sql
      ├─ 03-verify.sql
      └─ 04-rollback.sql
```

共享数据库 DDL MUST 在只读预检、SQL 与影响展示以及明确授权后执行。目录结构、命名、授权、验证和回滚的详细要求以[数据库与 SQL 规范](05-数据库与SQL规范.md)及 `sql/README.md` 为准。

## 7. 配置与 Secret

- 项目元数据、依赖声明和工具静态配置 MUST 位于 `pyproject.toml`；MUST NOT 在多个互相冲突的配置文件中重复维护同一设置。
- 运行期可变值和 Secret MUST 通过环境变量或受信任的 Secret 注入进入配置对象；业务模块 MUST 依赖类型化配置对象，MUST NOT 到处直接读取环境变量。
- 配置对象 MUST 在应用组合根完成解析和校验，MUST 对缺失、非法范围和冲突配置快速失败。
- 密钥、令牌、连接串、真实账户、个人信息和生产数据 MUST NOT 写入源码、测试样本、Prompt、日志、数据库配置表或仓库文档。
- 非敏感示例值 MAY 写入示例配置，但 MUST 使用明显无效的占位值并说明注入方式。
- 配置键属于 Provider 实现细节时 MUST 在 Provider 内映射，上层 MUST NOT 感知厂商专有键。

## 8. 命名规则

| 对象 | 规则 | 示例 |
|---|---|---|
| Python 包、模块 | MUST 使用小写 `snake_case`；名称 MUST 表达单一职责 | `plan_execute`、`error_mapping.py` |
| 类、Protocol | MUST 使用 `PascalCase`；Protocol SHOULD 使用角色名而非 `I` 前缀 | `RunContext`、`ToolExecutor` |
| 函数、方法、变量 | MUST 使用小写 `snake_case` | `resolve_strategy`、`run_id` |
| 常量、环境变量 | MUST 使用大写 `UPPER_SNAKE_CASE`；环境变量 SHOULD 以项目或能力前缀隔离 | `DEFAULT_TIMEOUT_SECONDS` |
| 测试文件 | MUST 使用 `test_<subject>.py` | `test_dependency_rules.py` |
| 测试样本 | SHOULD 表达领域与场景；MUST NOT 使用 `data1.json` 等无语义名称 | `tool_timeout_response.json` |
| Prompt/Schema/资源 | MUST 有稳定英文或数字 ID，文件名 SHOULD 使用 `snake_case`；版本 MUST 通过元数据管理 | `strategy_router_v1.jinja2` |
| 配置字段 | MUST 使用 `snake_case`；外部厂商键 MUST 仅在 Provider 边界映射 | `request_timeout_seconds` |
| 文档 | MUST 遵循文档治理规范的中文主题和稳定前缀 | `2026-09-01-Graph运行时-设计.md` |
| SQL 目录和对象 | 目录 MUST 使用 `YYYYMMDD_NNN_中文主题`，数据库对象 MUST 使用小写 `snake_case` | `20260901_001_agent运行状态` |

代码标识符 MUST 使用英文；中文注释 MAY 保留标准英文技术术语。同一模块 MUST 保持一致风格。

## 9. 依赖声明与锁定

- 直接和开发依赖 MUST 在 `pyproject.toml` 中按用途声明，MUST NOT 只存在于某台机器的全局环境或临时安装命令中。
- 项目目标使用 `uv` 管理环境和锁文件。引入首批第三方组件并完成兼容性验证后 MUST 生成、评审并提交 `uv.lock`，以形成 Windows/Linux 可重复安装目标。
- 当前 `dependencies = []` 的标准库骨架 MAY 不存在 `uv.lock`；此状态 MUST NOT 被表述为第三方依赖已经锁定或 Python 3.12 兼容性已经验收。
- 新依赖 MUST 说明用途、许可证、安全与维护状态、传递依赖、替代方案和移除策略；功能重叠的库 SHOULD 复用既有选型。
- 生产依赖与仅测试/开发依赖 MUST 分组；未在项目配置中声明的工具 MUST NOT 被列为当前必过门禁。
- 依赖升级 MUST 更新锁文件并运行受影响的单元、契约、集成、安全和质量回归。

## 10. 生成文件、缓存与敏感文件

以下内容 MUST NOT 作为源码或治理产物提交：

- `__pycache__/`、`*.pyc`、测试缓存、类型检查缓存、Lint 缓存；
- 本地虚拟环境、IDE 用户配置、临时下载、构建产物和覆盖率原始数据；
- 模型下载缓存、OCR 中间件、抓取页面、临时索引、数据库转储和运行 Artifact；
- 含密钥、令牌、连接串、Cookie、真实 Prompt 输入、个人信息或生产数据的文件；
- 可由稳定源码和锁文件重复生成且没有评审价值的文件。

需要纳入版本管理的生成产物 MUST 声明生成器、版本、输入、重建命令、所有者和是否允许人工编辑。测试生成文件 MUST 使用临时目录并在测试结束后释放。

## 11. 结构变更门禁

新增顶层目录、一级包、跨层模块或新的公共生命周期前，执行者 MUST：

1. 证明现有边界无法表达该职责；
2. 更新已批准设计，或为架构裁决创建 ADR；
3. 明确所有者、输入输出、依赖方向、失败语义和测试位置；
4. 同步目录文档、规范索引和 AST 架构守卫；
5. 在交付证据中列出新增边界和验证结果。

执行者 MUST NOT 通过动态导入、字符串导入、运行期注册副作用或重导出来规避依赖守卫。架构守卫尚未覆盖的规则仍然有效，评审者 SHOULD 要求补充自动化。
