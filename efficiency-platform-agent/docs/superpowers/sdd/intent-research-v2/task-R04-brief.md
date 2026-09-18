# R04 Tool 注册、执行账本与错误保真任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R04 |
| 状态 | 离线通过 |
| 依赖 | C03、R03 离线通过 |
| 范围 | Agent 侧研究 Tool、AcquisitionExecutor、SourceAttempt 账本与重试策略 |

## 不变量

1. 只显式注册 `research.discover.v2`、`research.fetch.v2`；Tool 参数不接受 tenant、run、lease、真实凭据或 authorization digest。
2. 可信范围由 `RunContext` 与服务端 ScopeResolver 注入；未知来源、跨租户/Run 或未准入来源在 Provider 前拒绝。
3. Provider 只调用一次；Tool Runtime 的研究 Tool `max_attempts=1`，有界重试统一由 AcquisitionExecutor 负责。
4. SourceAttempt 区分 success、success_empty、failed、truncated、cancelled，并保留 coverage、cursor、HTTP 状态、lease、过滤数与用量。
5. 429/403/Schema/SSRF 等来源原因通过版本化结果保真；外部 ToolError 只暴露枚举码和固定安全文案。
6. 同一 tenant/run/action 幂等重放不重复调用或扣费；不同 Run 不共享执行结果或尝试历史。
7. 取消、deadline 和迟到响应不交付成功；每次真实派发均只通过一个预算结算路径。
