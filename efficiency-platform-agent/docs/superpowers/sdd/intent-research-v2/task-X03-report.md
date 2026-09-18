# X03 实施报告：全链路离线、攻击与故障验收

## 状态

**离线通过。**

X03 已接通真实 `ConversationService → IntentPipelineV2 → Scenario/Supervisor → LangGraphResearchServiceV2 → ToolRuntime → Fake 免费来源 → Delivery`。该结论只覆盖离线 Fake 与内存状态，不代表真实来源、真实模型、PostgreSQL 恢复或生产开关已验收。

## 关键实现

- 新增 `ResearchV2ProviderAdapter`，既有 Supervisor Research Specialist 只能经冻结 Brief 调用 ResearchService V2；异常统一收敛为稳定错误码且不泄漏 canary。
- 修正研究身份传播：Provider 请求使用 operation task_id，不再使用所有研究场景共用的步骤名 `research`，避免并发任务 Brief 串用。
- 新增内存 Brief 交接存储、真实 Intent V2 Run delegate、可信输入工厂和 `industry_digest` 提交构建器；不构造伪 V1 confidence。
- 组合根在 V2 开启时强制 Supervisor 使用 V2 Provider adapter，并强制 Delegate 与图 resolver 共享同一个 `ConversationSubmissionStore`。
- 本地确定性聊天在 V2 前返回，普通问候不进入意图模型或采集链。
- 保持单一 Harness GraphRuntime；Research V2 只有一个 StateGraph，Agent/Graph 无直接 HTTP、socket、OpenAI SDK 或解析库联网。

## 主验收切片

固定时钟 `2026-09-16 09:41+08:00`，输入“收集昨天 AI 行业新闻，选 5 条”：

- Intent V2 将“昨天”固定为 `[2026-09-14T16:00:00Z, 2026-09-15T16:00:00Z)`，三轮请求没有扩大窗口。
- ToolRuntime 调用 Fake 免费来源三轮，返回 `3 + 1 + 0` 条。
- Research Graph 在两次补采后以 `ROUND_LIMIT` 停止，交付 `PARTIAL`、4 个事件、4 组引用。
- Supervisor 继续生成带引用的行业简报，Run 终态为 `SUCCEEDED`；请求精确 5 条未被伪报完整。
- 脱敏证据见 [JSON](task-X03-offline-evidence.json) 与 [SSE](task-X03-offline-evidence.sse)。

## R01—R23 故障矩阵

| 设计项 | 验收证据 |
|---|---|
| R01、R09、R10 | X03 主闭环：同一昨天窗口、exact 5 仅交付 4、3+1+0、ROUND_LIMIT |
| R02—R04 | `test_deduplication.py`、`test_event_clustering.py`、`test_normalization.py` |
| R05、R12、R13 | `test_claims.py`、`test_output_verifier.py`、`test_delivery.py` |
| R06—R08、R11、R23 | `test_acquisition.py`、`test_adapters.py`、`test_replay_manifest.py`、`test_quality.py` |
| R14、R15 | `test_research_transport.py`、`test_research_v2_boundaries.py`、交付 HTML/Markdown 注入用例 |
| R16、R19 | 原子预算/Tool Runtime 竞态、取消、迟到与硬截止测试；X01 跨进程恢复仍阻塞 |
| R17、R18 | UNKNOWN_OUTCOME 与跨进程幂等属于 X01 授权阻塞，本轮不以 Fake 冒充 |
| R20 | V2 默认关闭、旧搜索互斥、V1 adapter 与组合根回归 |
| R21、R22 | 来源目录仍 disabled/UNVERIFIED；真实费用与免费额度留给 X04，不发起试探请求 |

## 验证证据

```text
X03 聚焦组合：59 passed
Conversation/V2 顺序与主闭环：13 passed
全量离线回归：1458 passed, 275 subtests passed, 2 known warnings in 49.03s
源码与测试 Ruff：All checks passed
mypy：Success: no issues found in 270 source files
compileall：退出码 0
文档治理：23 passed, 117 subtests passed
```

仓库根 Ruff 额外扫描到 `docs/superpowers/sdd/*` 历史快照中的 53 个既有问题；这些快照不属于本任务运行代码，未批量改写。两条测试警告仍为既有 Starlette deprecated alias 与 Polars FutureWarning。

## 未完成边界

- X01 仍因无授权隔离 PostgreSQL、DDL、retention 与 UNKNOWN_OUTCOME 决策而阻塞。
- 没有访问真实 API/RSS/网页，没有验证来源免费性、许可、可用性或真实 DNS/TLS 行为。
- 没有调用真实模型、读取 `.env`、启动服务、执行 Git、Java/UI、部署或共享 DDL 操作。
- X04、X05 仍未开始；V2 默认关闭且 memory backend 不具备生产就绪资格。
