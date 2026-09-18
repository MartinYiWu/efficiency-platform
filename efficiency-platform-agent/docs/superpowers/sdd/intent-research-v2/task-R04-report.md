# R04 实施报告：研究 Tool、执行账本与唯一重试层

## 状态

**离线通过。**

R04 已完成研究发现/取文 Tool 的显式注册、可信运行范围注入、AcquisitionExecutor 唯一重试层、来源尝试账本、逐 Tool 与逐 HTTP 预算租约，以及取消/截止/迟到响应治理。没有启用真实来源、没有发起公网请求、没有读取真实凭据，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/tools/external/research.py`
- `src/efficiency_platform_agent/capabilities/research/v2/acquisition.py`
- `src/efficiency_platform_agent/capabilities/research/v2/attempts.py`
- `src/efficiency_platform_agent/tools/runtime/service.py`
- `src/efficiency_platform_agent/contracts/research_sources_v2.py`
- `src/efficiency_platform_agent/providers/research/transport.py`
- `src/efficiency_platform_agent/providers/research/_adapter_support.py`
- Feed、GitHub Releases、HN 对请求计数与限流元数据的适配更新
- `tests/unit/tools/test_research_tools.py`
- `tests/unit/capabilities/research_v2/test_attempts.py`
- `tests/unit/capabilities/research_v2/test_acquisition.py`
- 安全传输与三类 Provider 契约反例更新

## 已实现不变量

- 只注册只读 `research.discover.v2` 与 `research.fetch.v2`；公开参数拒绝 tenant、run、lease、凭据及授权摘要，可信 scope 只由 `RunContext + ResearchToolScopeResolver` 注入。
- Tool 返回必须与请求的 request、candidate、source、lease 一致；跨来源或错配身份即 `SOURCE_SCHEMA_INVALID`，不能进入账本或后续证据链。
- 研究 Tool 的 `max_attempts=1`；Provider 与传输层不暗中重试。只有 AcquisitionExecutor 对 `SOURCE_RATE_LIMITED`、`SOURCE_TEMPORARY_FAILURE` 最多额外重试两次。
- 429 保留 `Retry-After`、HTTP 状态和限额信息；401/403/Schema/SSRF 类错误不重试。退避受绝对截止和取消信号约束。
- 同一 tenant/run/action 的相同动作幂等重放不再次调用或扣费；相同 action_id 的不同参数被拒绝，不同 Run 不共享结果、锁或尝试历史。
- Tool 重试使用独立而稳定的租约 invocation；每次真实派发只结算一次，前置权限/来源拒绝不扣本地调用额度，父租约是权威额度时不受陈旧本地快照误拒绝。
- 安全传输的每个 HTTP 请求、分页调用和重定向跳分别执行 `reserve -> mark_dispatched -> settle`；第二跳额度不足时在连接前停止。实际请求数进入 `FetchedContentV2.request_count` 和 `SourceUsageV2.requests`。
- SourceAttempt 区分 success、success_empty、failed、truncated、cancelled，保留 action、source、coverage、cursor、HTTP、限流、Retry-After、lease、过滤数与用量。Tool 边界异常和运行中取消也形成安全、无原异常正文的尝试事实。
- 已存在的成功动作不会因后续来源失败被删除；失败批次仍保留，供后续质量层决定 PARTIAL/FAILED。
- 取消在派发前、Provider 等待中及重试退避中均可终止；取消 scope 被标记终态。迟到成功只记尝试/预算审计，不作为可交付批次返回。
- ToolError 对外只使用枚举码与固定安全文案；原异常正文、响应体及凭据不进入结果或 SSE 边界。

## 验证证据

```text
R04 定向（Tool/Acquisition/Attempt/Runtime/Transport/三 Provider）：84 passed
R01—R04 + contracts + Research V2 + architecture：189 passed, 124 subtests passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 246 source files
全量回归：1335 passed, 275 subtests passed, 2 existing dependency warnings in 43.34s
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R04 引入。

## 边界与后续

- `InMemorySourceAttemptLedger`、内存动作结果和内存 BudgetLease Repository 仅用于离线契约；数据库 CAS、唯一约束、重启恢复与未知结果认领属于 X01。
- 真实 Provider/Connector 仍未装配；`config/research_sources.toml` 中全部来源继续保持 `enabled=false`、`UNVERIFIED`、`cost_mode=unknown`。
- R04 只建立受治理的采集执行事实，不把 Candidate 当证据；时间过滤、正文规范化与文档去重由 R05 实施。
- HTTP-date 形式的 Retry-After 尚未作为独立策略输入；当前稳定契约保存并执行有界秒数值，超出一天的值保守封顶且会被本阶段短截止阻止重试。
