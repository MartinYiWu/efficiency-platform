# X05 阶段报告：单租户灰度、停止与回滚

| 属性 | 内容 |
|---|---|
| 状态 | 真实单租户灰度通过；Agent 侧阶段关闭 |
| 验收日期 | 2026-09-17 |
| 租户 | `tenant-x05-canary` |

## 真实灰度结果

在一个 PostgreSQL 父 BudgetLease 下执行 20 个有效请求，五类用例各 4 次：14 次 PASS、6 次 PARTIAL、0 次 FAILED。PARTIAL 均为严格时间窗内免费公开信息不足，没有扩窗、补造或丢失引用。

来源读取只执行一次：Google RSS 1 次、GitHub Atom 1 次、HN 13 次；后续请求复用同一缓存，未重复采集。数据库最终记录 35 次外部调用（15 次来源 + 20 次模型）、8324 input tokens、43862 output tokens。Provider 未返回货币成本，因此费用仍标记不可观测。

完整脱敏证据见 `task-X05-live-canary.json`，其中五类计数均为 4、引用覆盖均为 100%、模型均已验证；普通聊天没有来源调用。

## 硬停止与回滚

新增 `CanaryStopController`，任何模型/来源未验证、正式事实引用不足、未准入来源或预算超发都会锁死后续调度。验收在 20 次正常请求后注入一条确定性的未准入来源观察：停止状态生效、下一次 dispatch 被拒绝、数据库调用数在触发前后均为 35、触发证据仍保留。

既有离线回滚测试继续覆盖：新会话单租户 allowlist、V1/V2 双向冻结、关闭补采仅影响新会话，以及运行中 V2 成功/等待/取消都不交给 V1、不删除 Checkpoint/Evidence。

## 验证

- X05/真实执行器定向测试：通过。
- Agent 全量：`1544 passed, 9 skipped, 280 subtests passed`。
- 治理/架构：`129 passed, 246 subtests passed`。
- Ruff 全 `src/tests/scripts`、mypy 299 个源码/脚本文件、compileall：退出 0。

## 边界

本轮没有修改生产配置、部署服务、执行共享 DDL、扩大租户或发布前端。意图影子评测使用 X04 已批准的独立真实评测证据；X05 没有再创建第二条研究分支，因此没有重复采集、Run、Checkpoint 或用户输出。X04 事件聚类量化已在明确标注为合成的冻结盲测上达标，故 Agent 侧阶段按批准范围关闭；仍不标记生产可用。
