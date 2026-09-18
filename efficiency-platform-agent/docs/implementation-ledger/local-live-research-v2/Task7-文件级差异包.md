# Task 7 正式会话组合根、语义入口与跨轮改写差异包

状态：实现及离线组合验证完成，待主任务独立复核；更新时间：2026-09-18。仅覆盖 Task 7，未开始 Task 8/9。

## 边界与文件白名单

本 Task 在永久非 Git 项目完成，未读取 `.env`，未执行 Git、真实网络/模型、服务启停、UI、Java、数据库、部署或生产切换。所有 HTTP、DNS、模型均只在测试边界注入替身；正式业务链仍使用真实 IntentPipelineV2、LangGraphResearchServiceV2、Task 5 StageRunner、Task 6 Materializer、Supervisor 和 ASGI 路由。

新增：

- `src/efficiency_platform_agent/harness/local_live_research_factory.py`：local_live 组合根。
- `src/efficiency_platform_agent/harness/local_live_references.py`：同身份、未过期 V2 ranked digest 引用闭包校验。
- `tests/unit/harness/test_local_live_research_factory.py`。
- `tests/integration/test_local_live_research_conversation.py`。

修改：

- `src/efficiency_platform_agent/harness/local_real_factory.py`：显式 runtime_mode 分支、60 次/180 秒 local_live 默认父预算、全装配绑定和 Task3 回归。
- `src/efficiency_platform_agent/harness/intent_v2_delegate.py`：Run 级任务/策略、澄清续轮、容量/TTL。
- `src/efficiency_platform_agent/conversation/intent_v2_adapter.py`：Run 级版本快照、租户失败关闭、容量/TTL。
- `src/efficiency_platform_agent/conversation/service.py`：前置引用事实验证、V2 澄清续轮状态。
- `src/efficiency_platform_agent/orchestration/intent_v2/reducer.py`：首轮 chat 合法状态。
- `tests/integration/test_conversation_ranked_reference.py`、`tests/conversation/test_intent_v2_flow.py`：仅同步既有 Task3 严格 run_id 存储端口和 Task7 RunContext 测试替身，未放宽生产代码。

变更前完整快照位于 `task7-before/`；新增文件以当前内容纳入本差异包，未创建 Git 元数据。

## 正式装配与安全语义

- 组合根只接受显式 local_live、内存 backend、V2 版本、来源/租户 allowlist；禁用或未授权 source 在 registry 和会话入口失败关闭。
- 应用只创建一个 `LocalResearchNetworkLimits`；每个 Run 创建独立 Run key、BudgetExecutionBinding、body HTTP quota、取消监听和 deadline。Task 5 StageRunner、Task 6 Materializer、Acquisition/Content Runtime 共享同一 Run 的 store/key/binding/cancellation/deadline；ToolLeaseContext 仍挂同一父租约，免费 HTTP 仅显式预留零成本，模型成本仍由 ModelRuntime 真实记账。
- local_live Harness 默认父预算 60 tool calls、180 秒；binding 继续取父预算和 Harness 60 次/20 MiB/输出 token 25% 与输出时间 35 秒中较严值；正文 HTTP quota 固定每 Run 30 次，应用级 host/source 速率和并发门共享。V1 继续 10 次/300 秒默认。
- 每个 local_live Run 使用独立 task/research policy 快照；策略更新只影响新 Run。意图消息、版本、待澄清快照和 run-settings 有容量或 30 分钟 TTL，活动 Run 不因清理驱逐。
- 首轮 V2 chat 映射既有 DIRECT，缺参映射既有 WAITING_INPUT；补答可继续 V2 reducer，以新 Run、同身份意图帧和新父 binding 完成研究。来源白名单外、跨 tenant/user/conversation、过期/不存在事实、非排名内容、外部模型字段和坏 Citation 均返回既有 `CONVERSATION_REFERENCE_UNAVAILABLE`，不会触发模型或网络。
- 跨轮改写只从上一轮已交付且 output_verified 的 V2 ranked digest 选择明确 rank；item、摘要、时间、confidence、why、source_refs 与 facts 事件逐字段匹配，Citation provenance 逐字段匹配。改写 payload 仅含选中 item 和 citation 闭包，不再研究网络。

## TDD RED/GREEN 证据

| 范围 | RED | GREEN |
|---|---|---|
| 正式组合根、共享限流、同 Run 依赖和跨轮改写 | 首批 `4 failed`；成本预留和普通 chat/CLARIFY 另现红灯 | `178 passed, 124 subtests passed in 24.70s` |
| 同身份/TTL/闭包引用 | 过期事实 `1 failed, 8 passed`；两条 digest 在旧 10-call 预算下 `RESEARCH_UNAVAILABLE` | local_live 60-call/180s 修复后双条排名、过期/跨身份/篡改闭包通过 |
| 澄清续轮 | `2 failed, 2 passed` | 新 Run、同身份 frame、独立 binding 研究 `1 passed` |
| 旧严格 Run 端口漂移 | 组合首次 `169 passed, 2 failed` | 严格 run_id 测试替身最小同步后 `2 passed` |
| Task3–6 既有回归 | 无新增失败 | `361 passed, 9 skipped in 58.90s` |

## 精确验证命令与结果

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_local_live_research_factory.py tests/integration/test_local_live_research_conversation.py tests/integration/test_conversation_ranked_reference.py tests/conversation tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py tests/architecture -q --tb=short --show-capture=no
# 178 passed, 124 subtests passed in 24.70s

.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2 tests/unit/capabilities/research_v2 tests/unit/harness/test_research_local_runtime.py tests/unit/harness/test_research_local_tools.py tests/unit/harness/test_research_v2_provider_adapter.py tests/integration/research_v2 tests/integration/test_operation_deliverable_v2.py tests/api/test_operation_delivery_v2_events.py -q --tb=short --show-capture=no
# 361 passed, 9 skipped in 58.90s

.venv\Scripts\python.exe -m ruff check src tests scripts
# All checks passed!
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent
# Success: no issues found in 305 source files
.venv\Scripts\python.exe -m compileall -q src tests scripts
# exit 0, no output
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/conversation/intent_v2_adapter.py src/efficiency_platform_agent/conversation/service.py src/efficiency_platform_agent/harness/intent_v2_delegate.py src/efficiency_platform_agent/harness/local_live_references.py src/efficiency_platform_agent/harness/local_live_research_factory.py src/efficiency_platform_agent/harness/local_real_factory.py src/efficiency_platform_agent/orchestration/intent_v2/reducer.py tests/integration/test_local_live_research_conversation.py tests/unit/harness/test_local_live_research_factory.py tests/integration/test_conversation_ranked_reference.py tests/conversation/test_intent_v2_flow.py
# 11 files already formatted
```

命令均为离线验证；跳过项不代表真实共享 DB、服务、模型或公网验收。

## 当前文件 SHA-256

| 文件 | SHA-256 |
|---|---|
| `harness/local_live_research_factory.py` | `5C818854C411406142A43F20642E5AC9BFEB26F9248D2753E130927D962852B8` |
| `harness/local_live_references.py` | `40722A438448C12E4800892EC5C587879522E69D08208C50E7A1D95DA9D1F721` |
| `harness/local_real_factory.py` | `8087139D1315B8DA0E4702C6E1DDF6DD0B498E7EC7AA22A6EA068905D749D4F3` |
| `harness/intent_v2_delegate.py` | `F9F2BDD19CC6DA4ABB3AB31CE2D620119976E1FE4C0CCBA4850D2076C08151A6` |
| `conversation/intent_v2_adapter.py` | `99BE4514D2FF021B59AFBC7FDD3587C18508A498EE110FE950885F2FE370EEB0` |
| `conversation/service.py` | `D36028C1FAF92E7A3FB8C1293EA735728D380A3E1D420C59B7A48CCFDD6339BC` |
| `orchestration/intent_v2/reducer.py` | `4BA867236F72500DDC20A8C0BC9E4780A5AF5DB9E8140A93E6828C09BFE32445` |
| `tests/unit/harness/test_local_live_research_factory.py` | `D885E68C5C1FAE3492CFD962B79B625C2C1B0CC0C6C1D6557B36E83E946DCA20` |
| `tests/integration/test_local_live_research_conversation.py` | `EA6AEFDB6CE42F6203E3B67F1F2AD426CE699F4CEFC06215B56C6B013C9D9044` |
| `tests/integration/test_conversation_ranked_reference.py` | `526D80E2BA4FA8638C3CC00FBC9962D51F793F08D70F2646E6B1100F7142E2C0` |
| `tests/conversation/test_intent_v2_flow.py` | `A7BE4B5C5AE608F9E6BF3577EB423FE0F52E3BDF4EF640C9E52338B6DB685601` |

本差异包只证明离线组合、契约、架构和静态门；不声明 production_ready、真实外部验收或 Task 8/9 完成。
