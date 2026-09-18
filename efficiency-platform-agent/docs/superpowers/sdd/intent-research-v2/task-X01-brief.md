# X01 任务简报：意图/研究事实持久化、迁移与恢复

| 属性 | 内容 |
|---|---|
| 状态 | 集成通过（临时隔离库） |
| 依赖 | C03、I07、R09、R10 离线通过 |
| 执行范围 | Agent 侧独立 schema；不触碰共享数据库 |

## 目标与边界

补齐 Intent revision CAS、Research action fingerprint/decision、Budget Lease、UNKNOWN_OUTCOME 和 retention marker 的 PostgreSQL 权威事实；以双连接和新进程恢复证明，不使用 Fake 替代。迁移只在用户授权的本机临时隔离 PostgreSQL 执行，不改生产配置、不部署、不执行共享 DDL。

## 完成证据

迁移包、四类 Repository、7/30/90 天过期标记和 dry-run/apply retention 脚本均已实现。真实临时库完成 precheck、up、verify、rollback、重新 up/verify；`tests/integration/research_v2` 9 项通过。详细结果见 [X01 报告](task-X01-report.md)。
