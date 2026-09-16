### Task 4: 落地数据库与 SQL 治理

**Files:**

- Create: `sql/README.md`
- Create: `docs/standards/05-数据库与SQL规范.md`
- Create: `docs/templates/SQL变更说明模板.md`

**Interfaces:**

- Consumes: `AGENTS.md` 数据库授权红线、`SECURITY.md` 单条只读 SQL 规则、已批准设计中的 SQL 变更包结构
- Produces: 所有未来数据库变更必须遵循的脚本包与评审模板

#### Step 1: 编写 sql/README.md

必须给出完整目录范例：

```text
sql/changes/20260901_001_agent运行状态/
├─ 00-变更说明.md
├─ 01-precheck.sql
├─ 02-up.sql
├─ 03-verify.sql
└─ 04-rollback.sql
```

必须说明：

- 目录名 `YYYYMMDD_NNN_中文主题`；
- 每个文件的唯一职责；
- 执行顺序；
- `01-precheck.sql` 必须只读；
- 展示预检、实际 SQL、影响和回滚后，取得用户明确授权才可执行 `02-up.sql`；
- 事务、锁超时、语句超时、幂等、执行窗口；
- `03-verify.sql` 验证结构、数据和关键查询；
- `04-rollback.sql` 的可回滚边界与不可逆事项；
- 记录实际执行人、时间、环境、输出和异常；
- 禁止直接运行来源不明脚本、禁止密钥/真实隐私数据、禁止把大回填与结构变更混在同一事务。

#### Step 2: 编写 05-数据库与SQL规范.md

规则必须分级为 MUST/MUST NOT/SHOULD/MAY，文档状态为“评审中”。必须详细覆盖：

- 变更分类：Schema、索引、约束、数据修复、回填、清理、向量索引；
- 变更包目录与文件命名；
- 数据库对象统一小写 `snake_case`；
- 索引 `idx_<table>__<columns>`；唯一约束 `uk_<table>__<columns>`；外键 `fk_<from_table>__<to_table>`；检查约束 `ck_<table>__<rule>`；
- 表/字段语义、类型选择、主键、`created_at`/`updated_at` 时区、租户字段；
- NULL、默认值、约束与外键策略；
- 索引列顺序、选择性、重复索引、部分索引与 HNSW；
- DDL 锁、大表、在线/并发索引、分批回填和兼容窗口；
- 事务、锁超时、语句超时、幂等和失败恢复；
- SQL 注释解释原因/风险，参数化查询，禁止字符串拼接；
- LLM SQL 仅 AST 验证后的单条只读 SELECT，CTE 内部只读，拒绝 DDL/DML、SELECT INTO、多语句和数据修改 CTE；
- Secret、敏感数据和生产样本；
- Alembic 是迁移编排入口，原始 SQL 作为受审变更包；两者必须引用同一变更标识，禁止双重执行；
- 共享数据库必须预检、影响说明、明确授权、验证；
- 执行证据和回滚记录。

向量规则必须明确：现有索引固定 `text-embedding-v4 + 1024 + cosine`；禁止不同模型/维度混用同一索引；模型或维度变化必须新建索引版本，通过双写/回放/A-B 后切换；HNSW 参数调整必须有召回、延迟、内存和构建时间证据。

#### Step 3: 编写 SQL变更说明模板.md

使用与规范相同的元数据格式，文档状态默认“草案”。必须提供清晰 HTML 填写提示而非含糊省略号，固定字段包括：

- 文档状态、负责人、评审人、执行审批人；
- 关联 ADR、设计和实施计划；
- 目标环境、数据库、Schema、变更标识、变更类型；
- 目标、非目标、影响对象、数据规模；
- 现状与 `01-precheck.sql` 结论；
- 锁/性能/容量评估和兼容窗口；
- `02-up.sql`、执行顺序、事务边界、超时；
- 授权记录；
- `03-verify.sql` 及通过标准；
- `04-rollback.sql`、触发条件、不可逆事项；
- 实际执行时间、执行人、输出、异常、最终结论。

模板本身不得包含真实连接、密钥、生产隐私数据或虚构审批结果。

#### Step 4: 验证

运行：

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_sql_rules_require_precheck_authorization_and_rollback -v
python -m unittest discover -s tests -v
```

Expected：SQL 聚焦契约 PASS；完整套件仍可因 Task 5-6 剩余文档保持 RED，但 Task 4 三个文件不得缺失，原有架构测试不得回归。报告记录 Python 版本及 ran/passed/failures/errors/skipped。
