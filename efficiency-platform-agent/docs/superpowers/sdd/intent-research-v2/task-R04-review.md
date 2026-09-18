# R04 规格与质量审查

## 审查过程

1. Tool 边界轮：验证仅有两个研究 Tool、参数无可信字段、未知 Tool/权限/来源在 Provider 前拒绝，输出身份必须与请求和可信 lease 对齐。
2. 错误保真轮：验证 401、403、429、408/5xx、Schema、传输失败和 URL 安全拒绝的分类；外部只出现固定安全文案，不回显异常或响应体。
3. 唯一重试轮：发现 Provider/Tool/Executor 多层重试风险，冻结研究 Tool `max_attempts=1`，仅 Executor 对两个暂态码最多执行三次总尝试。
4. 租约幂等轮：发现不同重试若复用 invocation 会被父账本误判为重复；改为 action/attempt 稳定独立键，并验证重放零新增调用、零新增扣费。
5. 截止与取消轮：覆盖派发前取消、Provider 等待中取消、退避中取消和迟到成功；取消优先于来源执行，迟到结果只保留审计。
6. 尝试账本轮：补齐 Tool 边界异常和运行中取消的 SourceAttempt，校验 tenant/run 隔离、批量原子写、相同事实幂等和冲突关闭。
7. HTTP 预算轮：发现仅在 Tool 层计一次无法覆盖重定向/内部请求；新增逐 HTTP 请求的父租约生命周期，第二跳额度不足时不连接。
8. 请求事实轮：把实际 HTTP 请求数从传输层贯穿到 FetchedContent、缓存重验证、Feed/GitHub/HN SourceUsage，避免“有重定向仍记一次”。
9. 污染与保留轮：验证跨来源 Provider 输出被拒绝，不同 Run 不共享状态，后续来源失败不会删除先前成功动作或尝试事实。
10. 分层轮：扫描 Provider 无 HTTPX/requests/socket 直接客户端，真实来源配置仍全部关闭；R04 未越权进入真实联网、持久化或证据判定。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 两个只读 Tool 与可信 scope 注入 | 通过 |
| Provider 输出身份/Schema 二次校验 | 通过 |
| 429/401/403/暂态/安全错误保真 | 通过 |
| Executor 唯一有限重试与 Retry-After 截止 | 通过 |
| action 幂等、冲突拒绝、跨 Run 隔离 | 通过 |
| Tool 与 HTTP 逐派发预算结算 | 通过 |
| SourceAttempt 全状态、字段和异常事实 | 通过 |
| 取消传播、退避中断、迟到不交付 | 通过 |
| 失败不删除既有动作结果 | 通过 |
| contracts/Research/architecture/全量回归 | 通过 |
| 真实来源免费性与公网可用性 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R04 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；本结论只覆盖离线执行治理与审计契约，不代表生产持久化、真实来源或公网连接已经验收。
