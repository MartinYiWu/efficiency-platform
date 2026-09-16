# Task 4 实施报告：数据库与 SQL 治理

## 1. 任务边界

- 唯一需求基线：`docs/superpowers/sdd/task-4-brief.md`。
- 实施范围：纯 Agent 侧数据库与 SQL 治理文档；未设计或修改 Java 侧架构，未涉及部署。
- 数据库动作：未连接任何数据库，未执行 DDL、DML、迁移、预检或授权操作。
- 版本管理：当前目录不是 Git 仓库，本任务未执行 Git 命令或提交。

## 2. 交付文件

| 文件 | 结果 |
|---|---|
| `sql/README.md` | 新建；定义五文件变更包、执行顺序、明确授权、事务/超时/幂等、验证、回滚、证据和禁止项 |
| `docs/standards/05-数据库与SQL规范.md` | 新建；状态为“评审中”，覆盖对象设计、索引、大表、运行期 SQL、安全、Alembic 和向量治理 |
| `docs/templates/SQL变更说明模板.md` | 新建；状态默认“草案”，使用 HTML 填写提示并预置待授权/待执行状态 |

除实施报告外，本任务只创建了 brief 指定的三个交付文件。

## 3. 关键裁决落地

- SQL 安全与 `SECURITY.md` 对齐：LLM SQL 必须通过 SQLGlot 完整 AST 校验，仅允许单条只读 `SELECT`；CTE 及嵌套查询也必须只读；明确拒绝 DDL、`INSERT`、`UPDATE`、`DELETE`、`MERGE`、`SELECT INTO`、多语句和数据修改 CTE。AST 通过后仍要求只读账号、只读事务、表列白名单、租户/权限策略、行数和超时限制。
- 共享数据库门禁：只读预检 → 展示实际 SQL/影响/回滚 → 用户针对本次变更和环境明确授权 → 执行 → 结构/数据/关键查询验证 → 必要时回滚并记录证据。SQL、环境、影响、窗口或回滚边界实质变化会使授权失效。
- 迁移单一执行权：Alembic 作为编排入口，受审原始 SQL 作为变更包；两者引用同一变更标识，并通过唯一执行模式及版本表/执行记录核对禁止双重执行。
- 向量一致性：现有索引固定 `text-embedding-v4 + 1024 + cosine`；模型、维度或距离不同不得混用同一索引；变化时新建版本，通过双写或回放、固定集 A/B 和可回退切换。HNSW 调参必须提供召回、P50/P95/P99 延迟、内存/磁盘、构建时间和写入影响证据。
- SQL 包与模板：统一 `YYYYMMDD_NNN_中文主题` 和 `00`～`04` 五文件职责，模板不含真实凭据、生产隐私数据或虚构审批结果。

## 4. 验证环境

- 实际解释器：Python 3.11.9。
- 项目目标基线：Python 3.12；本任务没有安装第三方依赖，未声称完成 Python 3.12 依赖兼容验收。

## 5. 验证结果

### 5.1 Task 4 关键标记检查

命令：PowerShell 对三个交付文件逐项检查状态、命名格式、SQL 安全、Alembic 防重复、向量固定配置、授权门禁、五文件结构和模板字段。

结果：`TASK4_MARKERS_OK`，退出码 0。

### 5.2 SQL 聚焦契约

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_sql_rules_require_precheck_authorization_and_rollback -v
```

结果：退出码 0；ran=1，passed=1，failures=0，errors=0，skipped=0。

### 5.3 全量测试

```powershell
python -m unittest discover -s tests -v
```

结果：退出码 1；ran=15，passed=14，failures=1，errors=0，skipped=0。

唯一失败为 `test_required_governance_documents_exist`，仍缺少后续 Task 5～6 负责的 8 个文件：

- `docs/standards/06-Agent-Prompt-Tool开发规范.md`
- `docs/standards/07-安全与数据治理规范.md`
- `docs/standards/08-可观测性与运行治理规范.md`
- `docs/standards/09-文档命名与变更治理规范.md`
- `docs/templates/架构设计文档模板.md`
- `docs/templates/ADR决策记录模板.md`
- `docs/templates/技术组件选型模板.md`
- `docs/templates/实施计划模板.md`

Task 4 的三个文件未出现在缺失清单中。原有 10 个架构测试全部通过，治理套件除上述后续文件存在性测试外均通过；未发现 Task 4 引入的架构回归。

## 6. 当前状态与未验证项

- Task 4 实施与本地契约验证已完成，三份文档仍分别保持规范要求的“评审中”或“草案”状态；未将内部实现完成误报为正式批准。
- 未验证真实 PostgreSQL、pgvector、Alembic revision、锁行为、生产规模、HNSW 性能或迁移执行；本任务只定义治理协议，不授权或执行数据库操作。
- 全量套件仍为预期 RED，关闭条件是 Task 5～6 补齐上述 8 个治理文档并重新执行全量测试。

## 7. 审查修复

### 7.1 修复内容

根据 Task 4 审查的三个 Important，对原三份交付文件完成以下修复：

1. 规范性术语统一：全面扫描 `docs/standards/05-数据库与SQL规范.md`，将规范性“必须”等中文表述改为 `MUST`、`MUST NOT`、`SHOULD` 或 `MAY`；条件性描述改为“确需”等非等级语句。扫描结果为 `NORMATIVE_TERMS_OK`。
2. 原子执行权：将“执行前查询 Alembic 版本表和记录”升级为目标数据库权威执行记录上的唯一约束与原子占用。补充 `claimed` → `running` → `succeeded` / `failed` 状态机、并发失败关闭、条件状态转换、失联恢复、失败重试、新授权与脚本实质变化使用新 `change_id` 的规则。明确 Alembic 版本表不是执行锁，`alembic_embedded`、`external_controlled`、`verify_only` 三种模式只能冻结一种；README 与模板同步增加 revision、模式、唯一执行者、权威记录、初始占位、原子占用和状态转换字段。
3. 只读 SQL 封闭策略：在 `SECURITY.md` 单条只读 `SELECT` 基线上进一步加严。新增全 AST 遍历、语句/表列/连接/运算符/表达式/函数版本化允许清单；未知、用户自定义、有副作用、外部访问和资源滥用节点默认拒绝。明确拒绝 `FOR UPDATE`、`FOR NO KEY UPDATE`、`FOR SHARE`、`FOR KEY SHARE`、`pg_sleep`、序列写函数、递归/无界高成本结构，并提供一个参数化安全允许示例和三个拒绝示例。

三份交付文件的审查修复关键标记检查结果为 `REVIEW_FIX_MARKERS_OK`。未修改本任务范围以外的项目文件，未执行 Git 或数据库操作。

### 7.2 审查修复后的新鲜验证

实际解释器：Python 3.11.9。

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_sql_rules_require_precheck_authorization_and_rollback -v
```

结果：退出码 0；ran=1，passed=1，failures=0，errors=0，skipped=0。

```powershell
python -m unittest discover -s tests -v
```

结果：退出码 1；ran=15，passed=14，failures=1，errors=0，skipped=0。

唯一失败仍是 `test_required_governance_documents_exist`，内容仍为 Task 5～6 尚未创建的同一组 8 个文件。Task 4 三个交付文件均存在，原有 10 个架构测试全部通过；本次审查修复未引入新的测试失败或错误。

## 8. 第二轮复审修复：一次性 Bootstrap

### 8.1 修复内容

第二轮复审指出首次创建 Agent Schema/权威执行账本时，普通账本原子占用机制尚不存在。已在三份 Task 4 交付文件中定义严格的一次性 bootstrap 协议：

- 固定路径 `sql/bootstrap/agent_database_bootstrap_v1/` 和固定 `change_id` `agent_database_bootstrap_v1`，仍使用 `00`～`04` 五文件结构；仅创建 Agent 独立 Schema、权威账本及其唯一/状态约束，不承载普通业务或向量变更。
- PostgreSQL 固定事务级 advisory lock 常量 `EFFICIENCY_AGENT_BOOTSTRAP_LOCK_V1 = 7887332933888385649`，登记归属为 `efficiency-platform-agent/database-bootstrap/v1`。明确其只协调同一目标 PostgreSQL 数据库的参与者，不声称跨数据库或跨集群通用。
- 替代互斥机制必须经 ADR 证明对同一目标的所有执行者具备强一致原子互斥、唯一所有者、fencing token、有限租约和 compare-and-set；进程、文件、线程锁或先查后建不等价。
- 执行协议固定为：锁外只读预检与分类 → 展示实际 SQL/锁/影响/回滚并取得显式授权 → 受控事务和有限超时 → 取得固定事务锁 → 锁内二次目录检查 → 同事务幂等创建 Schema/账本及登记 `claimed` → `running` → `succeeded` → 提交前验证所有权、唯一约束、状态约束、校验值和最小权限。
- 完整成功的重复 bootstrap 仅做幂等 no-op 验证；部分/不一致状态失败关闭并进入独立恢复设计。异常时整个事务回滚，事务锁随提交、回滚或连接终止释放；数据库外审计独立保存预检、授权、锁取得/释放、校验值、结果和异常。
- 普通变更明确禁止复用 bootstrap 路径、固定锁键、临时高权限和“账本尚不存在”例外；初始化完成后必须切回普通账本原子占用机制。
- SQL 变更说明模板已增加初始化类型/路径、bootstrap change_id、锁键/归属/作用域、替代互斥 ADR、锁外/锁内检查、同事务初始化、失败回滚/锁释放、外部审计、重复执行语义及实际锁证据字段。

规范性中文等级扫描结果：`NORMATIVE_TERMS_OK`。bootstrap 关键标记检查结果：`BOOTSTRAP_MARKERS_OK`。未修改本任务范围外文件，未执行任何数据库操作或 Git 命令。

### 8.2 第二轮修复后的新鲜验证

实际解释器：Python 3.11.9。

```powershell
python -m unittest tests.governance.test_documentation_contract.DocumentationContractTest.test_sql_rules_require_precheck_authorization_and_rollback -v
```

结果：退出码 0；ran=1，passed=1，failures=0，errors=0，skipped=0。

```powershell
python -m unittest discover -s tests -v
```

结果：退出码 1；ran=15，passed=14，failures=1，errors=0，skipped=0。

唯一失败仍为 `test_required_governance_documents_exist`，缺少项仍是 Task 5～6 负责的同一组 8 个治理文件。原有 10 个架构测试全部通过，本轮 bootstrap 修复未引入新的测试失败或错误。

## 9. S2 统一执行主链：版本化 Prompt Runtime（Task 4）

本节记录 S2 计划中的 Prompt Runtime Task 4；前文数据库与 SQL 治理内容保持不变。

### 9.1 交付范围

- `src/efficiency_platform_agent/prompts/runtime.py`：使用 `ImmutableSandboxedEnvironment` 与 `StrictUndefined` 的受控渲染器。
- `src/efficiency_platform_agent/prompts/resources/direct_system_v1.j2`：Direct 合成系统 Prompt。
- `src/efficiency_platform_agent/prompts/resources/workflow_draft_v1.j2`：Workflow 草稿 Prompt。
- `src/efficiency_platform_agent/prompts/resources/workflow_review_v1.j2`：Workflow 审校 Prompt。

Runtime 只读取显式 Registry 登记的模板；模板路径解析后必须位于固定 resources 根目录；变量集合必须与登记 Schema 完全一致；渲染错误、未定义变量、路径越界和超长结果均以中文稳定错误拒绝。用户变量只作为不可信数据插入，不进行二次 Jinja 求值；结果包装为带 Prompt 标识、语义版本、输出 Schema 版本和 `ProviderMessage` 的 `RenderedPrompt`。

三份模板均包含明确的不可信输入分区，输出约束统一为 `{"content": "非空字符串"}`，未写入业务平台规则、Secret 或真实数据。

### 9.2 验证证据

计划中的 RED 命令为 `uv run pytest tests/unit/prompts/test_prompt_runtime.py -q`。本次接手时目标文件已存在，无法复现“文件不存在”的历史 RED；新鲜执行结果为 `8 passed`，故报告不将其伪造为本轮 RED/GREEN 证据。

```text
uv run pytest tests/unit/prompts/test_prompt_runtime.py -q
8 passed in 0.09s

uv run ruff check src/efficiency_platform_agent/prompts
All checks passed!

uv run python -m compileall -q src/efficiency_platform_agent/prompts
退出码 0
```

随后按主线程要求移除该测试文件导入块后的多余空行，复跑 `uv run ruff check src/efficiency_platform_agent/prompts tests/unit/prompts` 已 `All checks passed!`。该格式修复不改变测试语义。真实 Provider、模型质量、生产运行和模板语义验收未执行。
