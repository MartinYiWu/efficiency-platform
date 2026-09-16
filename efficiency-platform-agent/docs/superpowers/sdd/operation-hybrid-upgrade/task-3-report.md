# Task 3：Supervisor 研究前置与分阶段执行报告

## 状态

DONE_WITH_CONCERNS

## 目标与范围

本任务在不修改 Java 侧、不新增联网数据源和不引入第二套 Graph Runtime 的前提下，完成 Supervisor 研究前置、Evidence Gate 校验、研究证据复用和研究失败关闭。研究 Provider 通过 `ResearchProviderPort` 注入，Supervisor 不直接实例化厂商 SDK。

## TDD 证据

### RED

先新增 `tests/acceptance/test_research_backed_multi_platform.py`，执行：

```text
uv run pytest tests/acceptance/test_research_backed_multi_platform.py -q
```

首轮结果：`2 failed, 1 passed`。失败原因是 Task 2 尚未把 `requires_research` 加入 `OperationTaskSpec`，测试在构造研究请求时得到 `TypeError: unexpected keyword argument 'requires_research'`，属于预期前置依赖缺失。随后补充“研究模式下平台仍输出 COPY 类型”和“研究 Provider 用量进入 Run 账本”的断言，分别先观察到平台类型和用量统计不符合预期，再按 TDD 修正。

### GREEN

Task 2 接线完成后重新执行：

```text
uv run pytest tests/acceptance/test_research_backed_multi_platform.py -q
```

结果：`4 passed`（包含补充断言）。

覆盖行为：

- 研究前置只调用一次 Provider，三个平台都收到相同来源引用；
- Provider 研究失败时在平台生成前关闭，平台模型调用次数为零；
- `requires_research=false` 时不调用 Research Provider，既有离线多平台行为保持。

## 实现内容

1. `ScenarioSupervisorAdapter` 增加注入式 `ResearchProviderPort`。
2. `requires_research=true` 且当前图不存在 `operation.research` 专用节点时，Supervisor 先执行研究阶段。
3. 研究阶段使用独立预算：超时 240 秒、最大输出 8,000 Token；Provider 异常、超时、返回契约非法均归一为稳定错误码。
4. 研究结果通过 `ResearchInsightAgent._evidence_pack` 转换为 `EvidencePack`，经过 `EvidenceGate`（至少 1 条有效来源、至少 1 个发布者、结论必须有来源、来源必须在时间窗内）后才进入平台派发。
5. 研究请求失败关闭，不允许平台 Specialist 生成无来源成品。
6. 研究成功后通过 Supervisor 请求中的 `evidence_pack` 投影来源引用，三个平台复用同一研究结果，不重复联网。
7. `OperationAgent` 显式持有研究 Provider；组合根负责将 Provider 注入 Supervisor。
8. 对已有包含 `operation.research` 节点的研究场景保留原专用研究 Specialist，避免同一请求重复联网。
9. 研究标志传递给平台 Specialist 以强制来源约束，但多平台成品仍保持 `COPY` 领域类型；仅 `research` 平台成品使用 `REPORT` 类型。
10. 研究 Provider 返回的 `UsageSnapshot` 记入当前 `OperationUsage`，避免研究阶段 Token/成本统计丢失。
11. 多平台渠道 Specialist 的单节点超时提高至 120 秒、输出上限提高至 8,000 Token，避免长文案结构化 JSON 被截断后产生部分交付。
12. 研究失败优先于预算判断：即使供应商失败响应携带异常大的 usage，也统一收敛为 `RESEARCH_UNAVAILABLE`，避免错误下沉为通用 Specialist 失败。
13. DeepSeek Responses API 的服务端搜索工具链用量与内容生成预算隔离；否则搜索上下文 Token 会在有有效证据时错误触发预算失败。
14. 快速意图路由补充“写一篇/推文/公众号”内容请求识别，今天的行业动态成文请求进入“研究前置 + 单平台成品”路径。

## 验证摘要

```text
uv run ruff check src/efficiency_platform_agent/orchestration/supervisor.py src/efficiency_platform_agent/agents/operation/operation_agent.py src/efficiency_platform_agent/harness/operation_agent_factory.py tests/acceptance/test_research_backed_multi_platform.py
通过

uv run pytest tests/acceptance/test_research_backed_multi_platform.py -q
3 passed

uv run pytest tests/integration/test_operation_agent_runtime.py tests/acceptance/test_operation_supervisor.py tests/acceptance/test_operation_research_quality.py -q
30 passed

uv run pytest tests/acceptance/test_research_backed_multi_platform.py tests/integration/test_operation_agent_runtime.py -q
27 passed

uv run pytest tests/integration/test_operation_agent_runtime.py::test_failed_research_is_not_reclassified_as_budget_exhausted -q
1 passed
```

## 变更文件

- `src/efficiency_platform_agent/orchestration/supervisor.py`
- `src/efficiency_platform_agent/agents/operation/operation_agent.py`
- `src/efficiency_platform_agent/harness/operation_agent_factory.py`
- `src/efficiency_platform_agent/agents/operation/specialists/model_backed.py`
- `src/efficiency_platform_agent/agents/operation/specialists/model_backed_research.py`
- `src/efficiency_platform_agent/agents/operation/scenarios/manifests.py`
- `src/efficiency_platform_agent/orchestration/intent_fast_path.py`
- `src/efficiency_platform_agent/capabilities/research/deepseek_web_search.py`
- `tests/acceptance/test_research_backed_multi_platform.py`
- `docs/superpowers/sdd/operation-hybrid-upgrade/task-3-report.md`

Task 2 依赖文件由其负责人维护，本任务未修改 `task.py`、`conversation/service.py`、`contracts/stream_events.py`。

## 风险与后续

- 当前阶段事件（`research_started`、`research_completed` 等）由 Task 4 负责；本任务不直接发布 SSE 事件。
- 研究预置阶段预算已在 Supervisor 中集中声明，但尚未把实际阶段耗时和 Token 使用量写入阶段事件，待 Task 4 接线。
- 对已有 `operation.research` 图节点采用专用 Specialist 作为研究阶段，后续如需统一所有场景的阶段事件，应在 Task 4 统一抽象而不是增加第二次 Provider 调用。
- 本报告只包含离线固定 Provider 验证；真实 DeepSeek Web Search 验收由 Task 5 执行。
