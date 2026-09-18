# X01 阶段报告：PostgreSQL 持久化、迁移与恢复

| 属性 | 内容 |
|---|---|
| 状态 | 集成通过（临时隔离库） |
| 验收日期 | 2026-09-17 |
| 数据库范围 | 本机临时 PostgreSQL 18，独立数据库与 `agent_runtime` schema |

## 完成结果

- 新增 Intent revision CAS、Research action/decision、Budget Lease 与保留策略 PostgreSQL Repository；所有 SQL 均参数化并使用 tenant 复合键。
- 新增 bootstrap 与 `20260916_001_意图与研究V2` 迁移包；只在授权的临时隔离库执行预检、迁移、验证和回滚演练，未触碰共享数据库。
- 双连接验证 CAS 冲突、跨租户拒绝、已提交动作按 fingerprint 重放、调用后提交前崩溃记为 `UNKNOWN_OUTCOME`、Checkpoint 与业务状态独立提交。
- 终态与取消不复活；未知外部结果保守占用预算，只有策略允许且 Provider 可安全确认时才能重试。
- `scripts/research_v2_retention.py` 默认 dry-run；apply 需要显式 schema、租户与批准范围，按 HTML 7 天、证据摘录 30 天、脱敏元数据 90 天取更短期限，只过期标记，不删除证据。
- 回滚关闭新写但保留 V2 表、记录和旧读路径；迁移回滚演练不以 DROP 数据作为恢复手段。

## 验证证据

`AGENT_X01_TEST_DATABASE_URL=<临时隔离库> uv run python -m pytest tests/integration/research_v2 -q`：`9 passed`。测试包含两条独立连接与一个新进程恢复读取，覆盖 CAS、幂等、预算竞态、UNKNOWN_OUTCOME、终态和 7/30/90 天保留策略。

迁移目录已实际执行 `precheck -> up -> verify -> rollback`，随后重新 `up -> verify` 供 X04/X05 使用。连接地址和原始数据不写入报告；临时实例在最终验收后关闭。

## 边界

该结论只证明本机临时隔离 PostgreSQL 集成，不代表共享库 DDL、生产部署、多副本流量或灾备切换已经完成。项目未执行 Git 操作。
