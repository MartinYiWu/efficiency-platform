# 生成用量诊断与压缩协商离线验收

状态：本轮离线修复及服务加载完成；真实生成用量结算尚未验证。负责人：本轮执行代理。更新时间：2026-11-04（北京时间）。适用范围：Agent Provider 付费 HTTP 守卫。

## 结果与边界

已修复一个确定的编码协商缺口，并为未知用量补充安全诊断。不能据此声称昨日 14 次 Flash 未结算的唯一根因已查明，也不能声称三类问题真实验收已全部通过。

本轮真实付费请求为 0。没有重开预算、追溯退款或结算历史 unknown；混合题、通用题仍未发送。预算是风险上限，不是测试消费目标。

## 证据与实现

1. 当前生成 Provider 用自有 HTTPX SSE 解析，遇到 `[DONE]` 后继续读取到 EOF；不能把 OpenAI SDK 提前关闭推断成当前问题根因。完整合成响应能在原链路结算。
2. 本机 HTTPX 0.28.1 默认协商 `gzip, deflate, zstd`，而采集器仅支持 identity/gzip/deflate。守卫现在发送 `Accept-Encoding: gzip, deflate`，不再主动请求不可解析的 zstd。厂商若仍返回未知编码，继续保留 unknown。
3. 采集器只输出固定原因、受控编码和布尔状态：缺推理用量、非法/冲突用量、缺 DONE/终态/usage、SSE 截断、压缩损坏/不完整、超限和 DONE 后多余事件等。原严格接受条件保持不变。
4. 响应关闭后日志关联本地 reservation ID，并记录是否完整读取、正常关闭及成功结算；不记录请求、Prompt、回答、凭据、任意厂商字段、任意头值或异常正文。错误 HTTP 状态沿用既有账本审计。
5. 诊断日志异常使用既有 `suppress(Exception)` 模式隔离，不覆盖业务或取消结果；账本异常不被吞掉。仅原校验确实触发缺推理用量时使用专用原因码，非法 prompt 不误归因。

## 本次验证

第一批新增 20 项在未修改生产实现时全部预期失败，随后通过。审查补充“非法 prompt 且缺 reasoning”“日志 handler 抛错”两项，先观察 2 项失败再修复。最终新增 28 项全部通过，包含持槽取消、提前关闭、读取/关闭错误、脱敏、默认及显式编码协商；真实 Provider 实现经 MockTransport 的三字节分块 identity/gzip/deflate 均能结算完整推理用量。没有接触真实模型。

在 `efficiency-platform-agent` 目录执行：

```powershell
.venv/Scripts/python.exe -m pytest tests/providers/test_paid_usage.py tests/providers/test_paid_usage_compression.py tests/providers/test_paid_usage_diagnostics.py tests/providers/test_paid_http_guard.py tests/providers/test_paid_http_queue.py tests/unit/core/test_paid_budget.py tests/unit/persistence/test_paid_budget_ledger.py tests/unit/persistence/test_paid_token_accounting.py tests/unit/harness/test_paid_factory.py tests/api/test_paid_budget_scope.py tests/unit/agents/customer_service/test_paid_budget_failure.py tests/providers/test_deepseek_stream_contract.py tests/providers/test_deepseek_stream_fake.py tests/architecture -q
```

结果：**234 passed, 124 subtests passed in 32.81s**。这是与此次变更相关的回归及全部 AST 架构守卫，不能称整个仓库所有测试通过。修正后的最后一次相关回归仅运行一次。

```powershell
.venv/Scripts/python.exe -m ruff check src/efficiency_platform_agent/providers/paid_http.py src/efficiency_platform_agent/providers/paid_usage.py tests/providers/test_paid_usage_diagnostics.py
.venv/Scripts/python.exe -m mypy src/efficiency_platform_agent/providers/paid_http.py src/efficiency_platform_agent/providers/paid_usage.py
.venv/Scripts/python.exe -m compileall -q src/efficiency_platform_agent/providers/paid_http.py src/efficiency_platform_agent/providers/paid_usage.py tests/providers/test_paid_usage_diagnostics.py
```

结果：Ruff 通过；mypy 两个生产文件无问题；compileall 退出码 0。未引入依赖，未修改 Java、前端、业务 Prompt、模型策略或共享数据库 Schema。

独立只读文件级审查发现日志异常隔离 P2 与原因归类 P3，两项均已修正；复审确认未发现新增重要问题。未使用 Git 操作。

## 服务与总账

核实旧监听 PID 158220 的父进程为本会话记录的 14612 后，仅重启本会话 Agent。新 launcher PID 230492，监听 PID 241196，父子关系已核实。Java 仍为 PID 241736，未重启。Agent `/health/ready` HTTP 200、status=ok；Java `/actuator/health` HTTP 200、status=UP。

固定总账在本轮前后只读快照完全一致，两个历史授权均 `operator_stop`、在途为 0：累计 21 次付费 HTTP、保守计账 3.106252 元，其中已结算估算 0.006252 元、unknown 保留 3.10 元。该数字不等于已核对的供应商实际账单。

## 剩余工作

昨天的未知响应没有可追溯的采集状态，保持原预留。当前仅证明合成完整响应和失败边界符合预期；真实 Flash 是否正常结算，仍需要有效授权下的最小真实验证。原授权已经停止且截止时间已过，不自动续期。后续真实验证必须明确当前价格、剩余累计上限及截止条件，并继续遇到未知用量即停，不运行无界全量付费回归。

## 证据位置

本轮本地证据：`.local-acceptance/paid-usage-diagnostics-20261104/`，含实施前两个文件快照、最终文件差异、红绿测试日志、最终回归和静态检查日志、前后账本快照、健康及进程核对。原始本地账本未复制；快照仅含已有总账治理事实。

- [最终回归](final-offline-regression.log)
- [最终账本与健康](final-ledger-health.json)
- [进程核对](process-verification.json)
- [独立审查](review.json)
- [实施计划](../../superpowers/plans/2026-11-04-生成用量诊断与压缩协商-离线实施计划.md)
