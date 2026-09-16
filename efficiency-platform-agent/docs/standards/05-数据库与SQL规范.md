# 数据库与 SQL 规范

| 属性 | 内容 |
|---|---|
| 标题 | 数据库与 SQL 规范 |
| 状态 | 评审中 |
| 作者/负责人 | Agent 平台维护者 |
| 创建日期 | 2026-09-01 |
| 最后更新日期 | 2026-09-02 |
| 评审人/批准人 | 评审人：尚未指定；批准人：尚未批准 |
| 关联 ADR/设计/计划 | [Agent 侧技术组件选型](../architecture/Agent侧技术组件选型.md)、[安全基线](../../SECURITY.md)、[SQL 变更包规范](../../sql/README.md)、[Agent 侧工程规范体系实施计划](../superpowers/plans/2026-09-01-Agent侧工程规范体系-实施计划.md) |
| 替代关系 | 无 |
| 适用范围 | `efficiency-platform-agent` 纯 Agent 侧 PostgreSQL、pgvector、SQLAlchemy、Psycopg、Alembic 和 SQL 变更包 |
| 不适用范围 | Java 侧数据库设计、Java 表结构、部署拓扑与数据库实例运维 |

## 1. 原则与变更分类

Agent 数据 MUST 使用独立命名空间，MUST NOT 与 Java 表混写。数据库连接可复用不代表对象所有权共享；对象归属不明确时 MUST 停止设计或执行并完成所有权确认。

每次数据库变更 MUST 归入一个主要类型，并 MAY 声明多个次要类型：

| 类型 | 典型内容 | MUST 评估重点 |
|---|---|---|
| Schema | 表、列、类型、序列、命名空间 | 锁、表重写、读写兼容、回滚 |
| 索引 | B-tree、GIN/GiST、部分索引、HNSW | 构建锁、磁盘、写放大、查询计划 |
| 约束 | 唯一、外键、检查、非空 | 历史脏数据、验证方式、写路径影响 |
| 数据修复 | 修正确定的错误数据 | 选择范围、审计、幂等、不可逆性 |
| 回填 | 为新增语义分批填充历史记录 | 批次、水位、限速、可续跑、兼容窗口 |
| 清理 | 删除过期、冗余或违规数据/对象 | 保留策略、依赖、备份、不可逆性 |
| 向量索引 | 向量列、索引版本、HNSW 参数 | 模型与维度一致性、召回、延迟、内存、构建时间 |

变更说明 MUST 声明类型、对象、数据规模、目标和非目标，MUST NOT 用“优化”“调整”等无边界描述代替影响分析。

## 2. 变更包、标识与执行权

除第 2.2 节定义的一次性账本 bootstrap 外，所有 Schema、索引、约束、数据修复、回填、清理和向量索引变更 MUST 使用 `sql/changes/YYYYMMDD_NNN_中文主题/` 独立变更包，并 MUST 包含：

```text
00-变更说明.md
01-precheck.sql
02-up.sql
03-verify.sql
04-rollback.sql
```

文件职责、执行顺序和授权门禁 MUST 遵循 [`sql/README.md`](../../sql/README.md)。变更标识 MUST 与目录名一致并保持稳定；复制、重做或替代变更 MUST 使用新标识并记录替代关系，MUST NOT 覆盖历史执行证据。

Alembic MUST 是迁移编排入口，原始 SQL 变更包 MUST 是可独立评审的事实来源。Alembic revision 和变更包 MUST 引用同一 `change_id`，并 MUST 在评审时选择且冻结一种执行模式：

| 执行模式 | 唯一写入执行者 | 约束 |
|---|---|---|
| `alembic_embedded` | Alembic revision | Alembic MUST 先取得原子执行权，再执行受审 SQL；外部执行器 MUST NOT 执行同一变更 |
| `external_controlled` | 受控 SQL 执行器 | 外部执行器 MUST 先取得原子执行权；Alembic revision MUST NOT 再执行 SQL，且 MUST 仅在权威状态为 `succeeded` 后同步/校验版本 |
| `verify_only` | 无写入执行者 | 只允许 Alembic 外部纯只读验证；不得执行 revision、推进版本或写任何数据库状态 |

`verify_only` 的语义必须失败关闭：它只允许在 Alembic 外部使用只读身份执行目录查询、只读业务验证和文件/revision 映射核对。它不得执行 `alembic upgrade`、`alembic downgrade`、`alembic stamp` 或 `alembic current`，不得执行任何可能更新 Alembic 版本表的 revision，不得推进 revision，也不得写入权威账本。允许示例是“读取迁移文件并以只读 SQL 核对目标对象是否符合预期”；拒绝示例是“为校验 revision 而运行 upgrade/stamp/current”或“写一条账本记录证明已检查”。

任何会更新 Alembic 版本表、权威账本、Schema 或数据的操作都属于数据库写入，必须选择 `alembic_embedded` 或 `external_controlled`，并走明确授权、原子执行权、`claimed` / `running` / `succeeded|failed` 状态机、revision/校验值对账和失败恢复。`verify_only` 不是“执行一个只含校验代码的 revision”，也不得作为规避写入授权的模式。

### 2.1 原子执行权与权威状态

每个目标环境、数据库和 Schema MUST 有一个数据库内权威执行记录。记录 MUST 至少包含 `change_id`、执行模式、Alembic revision、`02-up.sql` 校验值、授权证据引用、执行主体、尝试次数、状态和时间戳。在同一目标执行命名空间内，`change_id` MUST 有数据库唯一约束；等价实现 MAY 使用包含目标环境、数据库、Schema 与 `change_id` 的唯一键，但 MUST 保证同一目标的同一变更至多有一条权威记录。

执行器 MUST 在取得明确授权后、第一次写操作前，通过单条原子插入或等价 compare-and-set 取得执行权，并把状态从不存在变为 `claimed`。只有实际插入该唯一记录的执行器 MAY 继续；唯一冲突、compare-and-set 影响零行或无法访问权威记录时 MUST 并发失败并停止，MUST NOT 采用“先查询再执行”的非原子检查。

权威状态 MUST 只允许以下受条件保护的转换：

```text
不存在 ──原子占用──> claimed ──开始执行──> running ──验证通过──> succeeded
                                      └──执行或验证失败──> failed
```

- `claimed` MUST 表示执行权已被唯一主体占用且尚未开始变更；`running` MUST 表示至少一个受审写步骤已开始。
- `succeeded` MUST 是终态；其他执行器看到该状态时 MUST NOT 重放，只 MAY 运行只读验证并核对脚本校验值。
- 并发执行器看到 `claimed` 或 `running` MUST 立即失败关闭或按受控策略退出，MUST NOT 接管、并行执行或覆盖主体。
- `running` 超过租约或窗口 MUST NOT 被自动视为失败。恢复人员 MUST 先只读核对数据库实际状态、脚本校验值与最后提交点，再以当前状态为前置条件原子标记 `failed`；状态已变化时操作 MUST 失败。
- 从 `failed` 重试 MUST 先完成部分执行影响评估、回滚或前滚方案、验证与新的明确授权。只有脚本校验值未变化且恢复方案允许原变更继续时，执行器 MAY 通过原子 compare-and-set 将 `failed` 重新占用为 `claimed` 并递增尝试次数；SQL 发生实质变化时 MUST 使用新 `change_id`，MUST NOT 改写旧记录。
- 每次状态转换 MUST 校验当前状态、执行主体和脚本校验值，并 MUST 追加尝试证据。历史 `failed` 尝试 MUST NOT 被删除或改写成成功。

Alembic 版本表 MUST 是迁移视图而不是执行权锁。`alembic_embedded` 模式 SHOULD 在数据库能力支持时把业务变更、权威状态 `succeeded` 与版本推进放在一致的事务边界；非事务 DDL MUST 声明提交点和恢复方式。`external_controlled` 模式下，Alembic MUST 仅在权威记录 `succeeded` 且 revision、`change_id`、脚本校验值一致后推进或确认版本。版本表与权威记录不一致时 MUST 停止并人工核对，MUST NOT 自动补执行。

### 2.2 一次性账本 Bootstrap

首次创建 Agent 独立 Schema 和权威执行记录表时，普通原子占用机制尚不存在。该引导悖论 MUST 仅通过固定包 `sql/bootstrap/agent_database_bootstrap_v1/` 和固定 `change_id` `agent_database_bootstrap_v1` 解决。bootstrap MUST NOT 使用普通 `sql/changes/` 编号伪装，也 MUST NOT 创建业务表、业务索引、向量索引或执行数据回填。

PostgreSQL 目标数据库的 bootstrap MUST 使用事务级数据库 advisory lock 串行化。锁常量 MUST 固定为 `EFFICIENCY_AGENT_BOOTSTRAP_LOCK_V1 = 7887332933888385649`，登记归属 MUST 固定为 `efficiency-platform-agent/database-bootstrap/v1`；实现、变更包和审计证据 MUST 记录相同常量、归属与脚本校验值。锁键 MUST NOT 由租户、环境变量、模型输出、时间或用户输入动态生成，MUST NOT 被其他任务复用。

该 advisory lock 只协调连接到同一目标 PostgreSQL 数据库并使用同一锁命名空间的参与者，MUST NOT 被描述为跨数据库、跨集群或跨不同数据库产品的通用分布式锁。目标数据库不支持该锁或执行身份无权使用时，替代机制 MUST 经单独 ADR 批准，并 MUST 对同一目标的全部 bootstrap 执行器提供强一致原子互斥、唯一所有者、fencing token、有限租约和 compare-and-set；进程锁、主机文件锁、线程锁和“先查询后创建”MUST NOT 作为等价机制。

bootstrap MUST 遵循以下门禁：

1. `01-precheck.sql` MUST 以只读身份核对目标数据库身份、Agent Schema/账本表是否不存在或完整存在、同名对象/约束冲突、DDL 权限、事务 DDL 能力、锁常量登记冲突和长事务。结果 MUST 分类为“完全不存在”“完整且已成功初始化”或“部分/不一致”。
2. 执行前 MUST 展示固定 bootstrap 包、实际 DDL、固定锁键及归属、目标数据库作用域、影响、超时、事务、回滚和审计方案，并 MUST 取得针对本次目标数据库的明确授权。普通 DDL 授权、历史环境授权或锁获取成功 MUST NOT 代替该授权。
3. 获授权执行器 MUST 开启一个受控事务，设置有限锁等待/语句超时，取得 `pg_advisory_xact_lock(7887332933888385649)`，然后 MUST 在锁内重新执行目录级只读检查以关闭预检后的竞争窗口。
4. 锁内结果为“完整且已成功初始化”且 Schema、账本结构、唯一约束、状态约束、固定 `change_id` 和脚本校验值全部一致时，执行器 MUST 以幂等 no-op 结束，只 MAY 追加外部审计和执行只读验证。
5. 锁内结果为“完全不存在”时，执行器 MUST 在同一事务中幂等创建 Agent 独立 Schema 和账本表，MUST 建立同一目标内 `change_id` 的唯一约束与 `claimed`、`running`、`succeeded`、`failed` 状态约束，再 MUST 登记固定 bootstrap 记录并按 `claimed` → `running` → `succeeded` 转换。提交前 MUST 通过系统目录验证 Schema 所有权、表定义、唯一约束、状态约束、bootstrap 校验值和最小权限。
6. 锁内结果为“部分/不一致”、校验失败、超时或任一步骤异常时，事务 MUST 回滚且 MUST NOT 自动删除、覆盖或猜测修复既有对象。事务级锁 MUST 随提交、回滚或连接终止释放；实现 MUST NOT 依赖人工解锁作为正确性条件。
7. 数据库事务回滚后账本可能不存在，因此外部受控审计 MUST 独立记录预检、授权、目标数据库标识、固定锁键/归属、锁取得/释放、事务结果、脚本校验值、异常和恢复决定。敏感连接信息 MUST NOT 进入证据。
8. 失败后重试 MUST 从新的只读预检开始并取得新的明确授权。完整成功后的重复 bootstrap MUST 仅走第 4 步 no-op；部分状态 MUST 进入独立恢复设计与授权，MUST NOT 盲目重放。

bootstrap 成功并验证后，所有普通变更 MUST 使用第 2.1 节账本原子占用机制。普通变更 MUST NOT 复用 bootstrap 路径、固定锁键、一次性 DDL 身份或“账本尚不存在”例外；bootstrap 所需临时高权限 SHOULD 在验证后撤销或收敛到普通运行身份无法取得的受控角色。

## 3. 对象与字段命名

数据库 Schema、表、字段、索引、约束、序列和别名 MUST 使用小写 `snake_case`；MUST NOT 使用需要双引号保留大小写的名称、模糊缩写或带环境名称的对象名。

| 对象 | 强制格式 | 示例 |
|---|---|---|
| 普通索引 | `idx_<table>__<columns>` | `idx_agent_run__tenant_id_created_at` |
| 唯一约束/唯一索引 | `uk_<table>__<columns>` | `uk_prompt_version__tenant_id_prompt_id_version` |
| 外键 | `fk_<from_table>__<to_table>` | `fk_agent_step__agent_run` |
| 检查约束 | `ck_<table>__<rule>` | `ck_agent_run__status_valid` |

索引名称中的 `<columns>` MUST 按索引列顺序排列；表达式过长时 MAY 使用稳定、可解释的缩写，但 MUST 在变更说明记录完整表达式。一个对象在各环境 MUST 使用相同逻辑名称，MUST NOT 以时间戳随机后缀规避冲突；版本化向量索引除外，其版本 MUST 显式可追踪。

表与字段名 MUST 表达单一语义和单位；时间、大小、持续时间等单位 SHOULD 进入字段名或被类型契约唯一确定。注释 MUST 解释领域含义、风险或兼容性，MUST NOT 只是复述名称。

## 4. 表、字段与租户边界

- 主键 MUST 有稳定、不可变且不承载可变业务语义的值；分布式写入 SHOULD 使用项目批准的 UUID/有序 ID 策略。MUST NOT 依赖展示名称作为主键。
- `created_at` 与 `updated_at` MUST 使用带时区的时间类型并统一按 UTC 存储；API 或展示层 MAY 转换时区。`updated_at` 的更新所有权 MUST 明确，MUST NOT 同时由互相冲突的触发器和应用逻辑维护。
- 租户数据表 MUST 包含不可为空的 `tenant_id`，唯一约束、普通索引和查询条件 MUST 把租户边界纳入设计。MUST NOT 仅依赖模型、Prompt 或调用约定隔离租户。
- 字段类型 MUST 按语义、范围、精度和查询模式选择；金额、计数、Token、向量维度和时间 MUST NOT 使用会丢失精度或语义模糊的类型。
- JSON/JSONB MAY 用于变化快、无需强关系约束的扩展元数据；核心状态、权限、租户键、排序键和高频过滤字段 MUST NOT 藏在无 Schema 的 JSON 中。
- 表、字段与枚举值的兼容性 MUST 在变更说明中定义；读写双方未完成兼容前 MUST 保留过渡窗口，MUST NOT 在单一步骤中完成不兼容的“加列、回填、切读、删旧列”。

## 5. NULL、默认值与约束

`NULL` MUST 只表达“未知或不适用”，MUST NOT 与空字符串、零、空数组混用表达同一状态。新增 `NOT NULL` 字段 MUST 先验证历史数据与写入路径；大表 SHOULD 采用添加可空列、分批回填、验证约束、再收紧的兼容步骤。

默认值 MUST 是确定、低成本且语义长期有效的值；MUST NOT 使用默认值掩盖调用方漏传必填信息。高成本或易锁表的默认值变更 MUST 分阶段实施。

数据库约束 SHOULD 用于守护跨入口都始终成立的数据不变量。外键策略 MUST 明确删除与更新行为、索引和锁影响；跨租户关系 MUST 同时约束租户一致性。`CASCADE` MUST NOT 在没有影响规模、级联深度和恢复方案时使用。暂缓验证的约束 MAY 用于大表渐进迁移，但 MUST 有明确验证步骤和退出条件。

## 6. 索引与查询计划

- 索引列顺序 MUST 依据实际查询的等值过滤、范围、排序和连接模式设计，MUST NOT 仅按字段出现顺序或主观猜测排列。
- 新索引 MUST 提供选择性、代表性查询计划、读延迟、写放大和空间成本证据。低选择性字段单列索引 SHOULD 避免默认创建。
- 创建前 MUST 检查等价、前缀覆盖、约束隐式创建和从未使用的重复索引；MUST NOT 用重复索引掩盖查询设计问题。
- 部分索引 MAY 用于稳定且能被查询谓词严格蕴含的热子集；变更说明 MUST 给出谓词、覆盖比例和未命中时的计划。
- 大表索引 SHOULD 使用数据库支持的在线或并发构建方式，并 MUST 说明其事务限制、失败后无效索引清理、磁盘峰值和复制影响。
- 查询计划证据 SHOULD 使用合成、脱敏或聚合信息；MUST NOT 把真实隐私数据或未经脱敏的参数写入文档。

### 6.1 pgvector 与 HNSW

现有向量索引 MUST 固定使用 `text-embedding-v4 + 1024 + cosine`。向量记录 MUST 保存或可追溯模型逻辑名、维度和索引版本；不同模型、不同维度或不同距离度量 MUST NOT 混用同一索引。

模型或维度变化 MUST 新建有版本号的向量列/索引空间，MUST 通过双写或可审计回放生成新向量，并 MUST 在固定评测集上完成 A/B。只有新版本在召回质量、延迟、内存和构建/回放成本达到批准阈值后 MAY 切换读取；切换 MUST 可回退，旧版本 MUST 仅在观察期和删除授权完成后清理。

HNSW 的构建参数与查询参数调整 MUST 提供同一数据集和负载下的召回、P50/P95/P99 延迟、索引内存/磁盘、构建时间及写入影响证据。MUST NOT 只凭单次查询或厂商默认值调参；参数变化 MUST 使用独立变更标识并保留旧值与回退条件。

## 7. DDL、大表与兼容窗口

变更设计 MUST 识别 DDL 锁级别、锁持续时间、表扫描/重写、磁盘临时空间、WAL/复制延迟和连接池影响。`01-precheck.sql` MUST 只读确认对象、规模、冲突索引/约束、长事务和执行前置条件。

大表变更 SHOULD 采用 expand → migrate → switch → contract：先添加兼容结构，再分批迁移/回填，切换读写并观察，最后在独立授权变更中移除旧结构。分批回填 MUST 有稳定游标或水位、批次大小、限速、暂停/续跑、影响行数与失败重试边界；MUST NOT 与结构变更放入同一大事务。

不支持在线/并发的操作 MUST 声明维护窗口和停机/降级边界。无法证明在窗口内安全完成时 MUST 先演练、拆分或停止执行，MUST NOT 以生产试错获得估算。

## 8. 事务、超时、幂等与失败恢复

- 每个写步骤 MUST 声明事务边界、隔离需求和提交点。数据库不支持事务化的操作 MUST 显式标注并给出中间状态恢复方式。
- 锁等待和语句执行 MUST 设置有限的锁超时与语句超时；数值 MUST 结合预检规模、演练和执行窗口评审，MUST NOT 直接复制任意默认值。
- 变更 MUST 设计为重复执行可安全判断“未执行、已执行、部分执行”并采取明确动作。幂等 MUST 依赖状态检查、约束或执行记录，MUST NOT 通过忽略所有错误实现。
- 超时、进程中断、网络断开或部分提交后，执行者 MUST 先只读检查权威状态，再选择续跑、前滚修复或回滚；MUST NOT 在状态未知时盲目重放。
- 失败恢复步骤 MUST 预先写入变更说明，包括停止条件、责任人、可接受数据损失、回滚耗时和不可逆事项。

## 9. SQL 编写与运行期查询

SQL 关键步骤的注释 MUST 解释原因、锁/性能风险、兼容性或恢复边界，MUST NOT 逐句翻译语法。SQL MUST 显式列出目标列，SHOULD 避免在稳定接口和持久化逻辑中使用 `SELECT *`。

应用查询值 MUST 参数化；表名、列名、排序方向等不能作为值参数的标识符 MUST 来自封闭白名单并使用驱动安全组合 API。MUST NOT 通过字符串拼接、格式化字符串、Prompt 拼接或模型原文构造 SQL。

当前禁止 Text2SQL、模型生成 SQL 和面向业务数据库的直接分析。模型文本、Prompt、结构化输出或 Tool/MCP 返回 MUST NOT 被拼接、解释或转换为可执行 SQL，也 MUST NOT 被用于动态选择未经封闭允许的表、列、Schema 或排序表达式。

Agent 自有运行数据查询 MUST 由受控 Repository 或明确的数据访问端口实现，值使用驱动参数化绑定；确需动态标识符时只能从代码内封闭映射选择。查询 MUST 继续执行租户/权限、语句超时、行数和结果大小约束。

未来若业务明确需要 Text2SQL，必须先重新完成需求边界、组件选型、威胁建模、数据源权限和失败关闭设计，并取得项目负责人明确批准；当前规范不预设 SQLGlot 或任何替代实现。

## 10. Secret、敏感数据与样本

密钥、令牌、密码、连接串、私有端点和生产凭据 MUST 通过受控 Secret 注入，MUST NOT 写入 SQL、Alembic revision、文档、注释、日志或测试样本。脚本 MUST NOT 切换到硬编码生产数据库或修改授权边界。

预检、验证和性能样本 SHOULD 使用合成、脱敏或聚合数据。确需使用生产统计信息时，访问与记录 MUST 遵循最小必要、权限、保留和审计要求；真实个人数据、完整 Prompt、敏感文档或可重识别行 MUST NOT 复制到报告、开发环境或评测集。

## 11. 共享数据库授权门禁

共享数据库 DDL 或数据写入 MUST 在执行前完成以下门禁：

1. 使用只读身份运行 `01-precheck.sql`，保存对象、规模、锁风险和前置条件结论；
2. 向用户展示变更标识、目标环境、实际 `02-up.sql`、影响、事务/超时、执行窗口和 `04-rollback.sql` 边界；
3. 取得用户针对该变更、环境和 SQL 的明确授权；历史同意、评审通过、合并、模板字段或默认审批 MUST NOT 代替本次授权；
4. 在授权范围内执行并保留不可篡改的时间、执行人、脚本版本和输出证据；
5. 运行 `03-verify.sql`，以预先批准的结构、数据、查询和租户边界标准判定；
6. 失败时按触发条件回滚或前滚，并记录所有异常和恢复结果。

SQL、环境、影响、执行窗口或回滚边界发生实质变化时，原授权 MUST 失效并重新申请。只读预检 MAY 在已授权的诊断范围内重复执行，但 MUST NOT 被扩大解释为写权限。

## 12. 验证、回滚与执行证据

`03-verify.sql` MUST 验证目标结构定义、约束/索引有效性、预期数据数量、租户隔离与关键查询计划/延迟；通过标准 MUST 在执行前确定。仅 HTTP 200、客户端退出码、无异常或对象存在 MUST NOT 单独构成完成证据。

`04-rollback.sql` MUST 描述安全可回滚范围、触发条件、执行顺序、预计时间和回滚后验证。删除、缩窄类型、不可逆转换、外部副作用或已承载新语义的结构可能无法无损恢复；此类事项 MUST 在授权前明确，且 MUST 提供备份/快照、停止写入、前滚修复或保留旧结构等补偿策略。无法安全自动回滚时 MUST NOT 提供会进一步破坏数据的伪回滚脚本。

每次执行尝试 MUST 记录变更标识、环境、数据库/Schema、执行人、审批人、授权证据引用、开始/结束时间、脚本校验值、事务边界、超时、输出摘要、影响行数、验证结论、异常、恢复/回滚动作和最终状态。证据 MUST 脱敏并按审计策略保留；MUST NOT 删除失败记录或把部分成功改写为成功。

## 13. 例外

对本规范 `MUST` 或 `MUST NOT` 的例外 MUST 按[工程规范索引](00-规范索引.md)记录规则位置、原因、备选方案、风险、补偿措施、责任人、批准者、期限/复审条件和恢复合规条件。租户隔离、Secret、禁止模型生成/执行 SQL 和共享数据库明确授权红线 MUST NOT 通过普通例外降低。
