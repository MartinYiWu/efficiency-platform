# S7 Task 5 实施报告：PostgreSQL/pgvector 隔离集成

## 实施范围

新增 PostgreSQL 注入式 Provider、Run/Event 运行仓储、Checkpoint 存储和 pgvector/原生 FTS 检索适配器。所有 SQL 使用参数占位符，Schema 仅接受 `s7_acceptance_[a-f0-9]{8}`，查询携带租户条件；向量空间固定为 `text-embedding-v4`、1024 维、cosine。适配器不在导入或构造阶段建立网络连接。

新增 `sql/changes/20260903_001_S7验收命名空间` 五文件变更包：只读预检、隔离 Schema DDL、只读验证和精确回滚。变更包不创建 `vector` 扩展，不引用业务命名空间。

## RED/GREEN 证据

RED：目标 Provider、Repository、Checkpoint 和 SQL 文件不存在时，契约测试在收集阶段因模块缺失失败。

GREEN：

```powershell
uv run pytest tests/contract/providers/test_postgres_provider_contract.py tests/governance/test_s7_sql_change_package.py tests/integration/s7/test_postgres_pgvector.py -q
```

结果：退出码 0，8 项测试通过；FakeConnection 仅记录 SQL 与参数，未建立真实连接。

静态检查：

```powershell
uv run ruff check src/efficiency_platform_agent/providers/database/postgres.py src/efficiency_platform_agent/persistence/postgres.py src/efficiency_platform_agent/orchestration/postgres_checkpoint.py src/efficiency_platform_agent/capabilities/retrieval/postgres.py tests/contract/providers/test_postgres_provider_contract.py tests/governance/test_s7_sql_change_package.py tests/integration/s7/test_postgres_pgvector.py
uv run ruff format --check src/efficiency_platform_agent/providers/database/postgres.py src/efficiency_platform_agent/persistence/postgres.py src/efficiency_platform_agent/orchestration/postgres_checkpoint.py src/efficiency_platform_agent/capabilities/retrieval/postgres.py tests/contract/providers/test_postgres_provider_contract.py tests/governance/test_s7_sql_change_package.py tests/integration/s7/test_postgres_pgvector.py
uv run mypy src/efficiency_platform_agent/providers/database/postgres.py src/efficiency_platform_agent/persistence/postgres.py src/efficiency_platform_agent/orchestration/postgres_checkpoint.py src/efficiency_platform_agent/capabilities/retrieval/postgres.py
```

以上针对本任务文件的三项命令均通过（format 检查以本次文件格式化后执行）。

2026-09-04 补充：Checkpoint 存储的 `get` 已按运行时标准返回 `CheckpointRecord`，并恢复 `resume_binding`；`GraphRuntime` 同时覆盖同步与异步 Checkpoint 存储调用，执行、恢复、读取和失败路径均传递 `tenant_id`。Run PostgreSQL 更新已携带 `expected_version`，创建或更新零行命中时归一化为 `RUN_VERSION_CONFLICT`。当时仅有 Fake/InMemory 离线证据；真实 PostgreSQL 验收已于 2026-09-07 按下文记录完成。

## 文件清单

- `src/efficiency_platform_agent/providers/database/postgres.py`
- `src/efficiency_platform_agent/persistence/postgres.py`
- `src/efficiency_platform_agent/orchestration/postgres_checkpoint.py`
- `src/efficiency_platform_agent/capabilities/retrieval/postgres.py`
- `tests/contract/providers/test_postgres_provider_contract.py`
- `tests/integration/s7/test_postgres_pgvector.py`
- `tests/governance/test_s7_sql_change_package.py`
- `sql/changes/20260903_001_S7验收命名空间/00-变更说明.md`
- `sql/changes/20260903_001_S7验收命名空间/01-precheck.sql`
- `sql/changes/20260903_001_S7验收命名空间/02-up.sql`
- `sql/changes/20260903_001_S7验收命名空间/03-verify.sql`
- `sql/changes/20260903_001_S7验收命名空间/04-rollback.sql`

## 剩余未验证边界

- 2026-09-07 已完成一次受独立授权约束的 G3 PostgreSQL/pgvector 真实验收：目标为 Agent 自有 `jjcy_ai_vector`，使用临时 Runtime 逻辑 DSN 映射，验证 Run/Event/Usage、乐观版本、跨连接 Checkpoint、1024 维 vector、原生 FTS、租户过滤及精确 Schema 回滚，证据见 `evidence/g3-postgres-network-probe.json` 与 `evidence/g3-postgres-pgvector-acceptance.json`。原始 `.env` 未修改；独立 Runtime 数据库提供后需在新目标重跑。
- 未验证目标实例已安装 `vector` 扩展、HNSW 索引可用性、权限、事务隔离和性能；本包明确不执行 `CREATE EXTENSION`。
- 未读取或修改 `.env`，未访问 Java/业务表；生产 DSN、费用、容量及备份恢复均未验证。
