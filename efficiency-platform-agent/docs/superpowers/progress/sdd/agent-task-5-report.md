# Task 5 R2：安全阶段、单一交付事件与受控后续动作实施记录

| 属性 | 内容 |
|---|---|
| 状态 | DONE_WITH_CONCERNS；R2 四项修复和离线门禁完成，待独立复核 |
| 负责人 | Task 5 实施 Agent |
| 适用范围 | 真实执行边界进度、V1 事件协议内的 V2/V1 单一交付、递归敏感载荷门禁 |
| 更新时间 | 2026-09-17 |
| 关联需求 | [Task 5 brief](agent-task-5-brief.md) |

## 复核结论与范围

Task 5 首轮独立复核未通过，指出四项必须关闭的问题：Harness 通过文本和整图返回伪造阶段、交付版本缺失时存在原始字典旁路、EventHub 递归敏感键不完整、进度计数依赖 `phase` 才校验。R2 已逐项先写失败测试再做最小修复；本报告只声明“修复完成，待独立复核”，不声明已批准。

完整阅读更新后的 brief、项目 AGENTS.md、三份架构文档、TDD/调试/代码审查技能及 Task 4 输出接口。项目永久 non-Git；未运行 Git 命令、未产生提交。批准范围新增 `core/operation_progress.py`，用于遵守现有层级矩阵；未修改依赖矩阵。

## R2 RED 证据

1. 删除伪阶段前，普通 fake Graph 测试得到 `4 failed, 3 passed in 0.82s`，证明 Harness 会按输入文本和整图结果补发阶段。真实节点信号测试最初得到 `2 failed, 1 passed, 30 deselected in 3.86s`，当时窄端口尚不存在。
2. 顶层版本缺失旁路测试得到 `3 failed, 5 deselected in 0.69s`：嵌套非法 V2 action/内部 extra 被旁路，双版本缺失的 V1 未严格规范化。
3. EventHub 新增四类递归敏感键后得到 `4 failed, 11 passed in 0.67s`。
4. `phase_started` 缺 phase、bool/负数/大小关系及非阶段事件计数测试得到 `10 failed, 31 passed in 0.75s`。
5. 复核补充的可信 phase 覆盖、混合波次计数和失败研究完成语义得到 `3 failed in 5.85s`。
6. 第一版 ContextVar 位于 runtime 并被低层直接依赖，AST 门禁得到 `1 failed, 11 passed, 47 subtests`；该红灯推动依赖反转，而不是放宽层级矩阵。

## 实际信号来源与阶段规则

进度窄端口的 ContextVar、六个受控进度事件和五个用户阶段定义在 `core/operation_progress.py`。`runtime/operation_progress.py` 仅为 Harness 提供薄重导出。Harness 只绑定当前 Run 发布器、让可信参数 `phase` 覆盖 payload 同名键，并对单 Run 的 `phase_started` 去重；它不分析用户文本，也不在 `graph_runtime.execute()` 返回后批量补阶段。

| 用户阶段 | 唯一真实来源 | 失败/跳过规则 |
|---|---|---|
| `understanding_request` | `OperationRuntime` 成功解析并校验 Submission 身份后 | 解析失败不报告 |
| `collecting_sources` | `ScenarioSupervisorAdapter` 即将调用真实研究 provider，或真实 `operation.research` 波次开始 | 没有研究调用/任务则省略 |
| `checking_evidence` | provider 结果通过证据门禁，或研究波次至少一个对应任务真实成功后 | 失败研究不发送 `research_completed` 成功事件 |
| `creating_content` | 非 `operation.research` 创作任务波次开始 | 没有创作任务则省略 |
| `checking_delivery` | `ScenarioPackService` 即将执行真实质量门禁 | 未进入质量门禁则省略 |

研究和创作混合波次分别按对应任务 ID 计算 `target`，`completed` 只统计对应类型且状态为 `SUCCEEDED` 的 outcome。研究失败不伪称完成。真实“解析 + 研究 + 创作 + 质量门禁”链的阶段顺序验证为：`understanding_request` → `collecting_sources` → `checking_evidence` → `creating_content` → `checking_delivery`。普通 fake Graph 不主动报告时阶段为空。并发 Run 的 ContextVar 发布器隔离，同一 Run 同阶段只发布一次。

## 单一交付与敏感信息门禁

- 保持 `run.stream.event/1`、原 `phase_started`、`deliverable` 和唯一 `stream_done`，未建立第二套流协议或动作执行事件。
- 顶层 `delivery_contract_version` 缺失时读取 `deliverable_set.contract_version`；两者都缺失时只按 `DeliverableSetV1` 严格校验。所有路径都重新序列化，永不原样透传字典。
- 非法 V2 action、嵌套 `hidden_reasoning` 或其他 extra 失败关闭：不发布 `deliverable`，只发布固定 `DELIVERABLE_SET_INVALID`，且原生命周期仍唯一结束。
- EventHub 递归拒绝规范化后的 `model_candidates`、`tool_args`、`raw_page`、`hidden_reasoning`；错误不回显敏感值。普通业务正文中的 `token` 单词仍允许，稳定凭据/连接串格式检测保持不变。
- `completed`、`target` 无论是否包含 `phase` 都独立校验：拒绝 bool、负数及 `completed > target`；`phase_started` 必须包含五值白名单中的 phase。未知内部阶段不得透传。

## GREEN 与最终验证

R2 修复后的聚焦组合：

```powershell
.venv\Scripts\python.exe -m pytest tests/api/test_operation_delivery_v2_events.py tests/api/test_operation_phase_events.py tests/api/test_run_sse_integration.py tests/contracts/test_stream_event_contracts.py tests/runtime/test_event_hub.py tests/integration/test_operation_agent_runtime.py tests/unit/operation/scenarios/test_service.py tests/unit/orchestration/test_operation_supervisor_builder.py -q
```

结果：退出码 0，`128 passed in 3.24s`。brief 指定的 API、SSE、回放和契约子集为 `72 passed in 3.47s`。

静态与架构门禁：

- 13 个 Task 5 Python 文件 Ruff check：`All checks passed!`。
- Ruff format check：`13 files already formatted`。
- 8 个生产文件 mypy：`Success: no issues found in 8 source files`。
- `.venv\Scripts\python.exe -m compileall -q src tests`：退出码 0。
- AST 依赖守卫：`12 passed, 47 subtests passed in 2.20s`。

最终全量：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

结果：退出码 0，`1693 passed, 9 skipped, 2 warnings, 280 subtests passed in 59.21s`。两条 warning 仍为既有 Starlette alias deprecation 与 Polars Excel future behavior。

## 文件快照清单

| 文件 | SHA256 |
|---|---|
| `src/efficiency_platform_agent/core/operation_progress.py` | `8715FD9AD68C75CCB21C3B413C1DD3354815FC591A76F6ACF91EC282F9CC2AC5` |
| `src/efficiency_platform_agent/runtime/operation_progress.py` | `CD542471C6DD93963EC941BA845BCAD9487C1E78494F42305B9D465AB220070C` |
| `src/efficiency_platform_agent/harness/service.py` | `889195F3C18CC23D408429883AB731BDDC8614237DCB4D1E0C8BE01FC6A60C83` |
| `src/efficiency_platform_agent/contracts/stream_events.py` | `D2490D258CE579ADAD1CDC1DFC84E4FBE6FB03D92CFC5338E27325286C1E3871` |
| `src/efficiency_platform_agent/orchestration/builders/operation_runtime.py` | `8DE5A83EC746FF61DAC1658BF1A63235AE8641FE3D0154AC2F434E887ADA6192` |
| `src/efficiency_platform_agent/orchestration/supervisor.py` | `5EA4DA0E48F92AC40AC9B76D2061C865A72AEB837468CA26B43ABC86D0E596E3` |
| `src/efficiency_platform_agent/agents/operation/scenarios/service.py` | `0953BD15AD75FFAB13A30087E2752FB64860A3957C041F1CE9E9282C1EFA65D0` |
| `src/efficiency_platform_agent/runtime/event_hub.py` | `DBAD1719EDD63099F0D5492F0D4CCB1927FD2A86EBE427008D7A33497BBCBC2F` |
| `tests/api/test_operation_delivery_v2_events.py` | `FCDB7A14CE0AC5FF4568D777F986432F91FBBC6B467CB85765EBA1487AE616E4` |
| `tests/api/test_operation_phase_events.py` | `4639DF4D3F560CF6A04D53243785417BDC0EA873C6DF65C7FF12DAD54B8A43EA` |
| `tests/contracts/test_stream_event_contracts.py` | `B7B653911E689C8711D9C90E90A819BEF122C76F4D43F9549985CA38EC3AFC95` |
| `tests/runtime/test_event_hub.py` | `39751A7AD6EB3437DEEA51C00DE52370288B14F5C221191DC087E832A4EBFEC4` |
| `tests/integration/test_operation_agent_runtime.py` | `52541DC7E8D549532C467474EC3451140E97D872BA2F936FFC026C90101CC0C1` |

R2 基线保存在控制器提供的 `agent-task-5-baseline-r2` 目录；首轮四文件基线仍保存在 `agent-task-5-baseline`。报告和正式账本不做自引用哈希。

## 状态与担忧

Status：DONE_WITH_CONCERNS。R2 四项实现修复、指定回归、静态门禁、架构门禁和全量测试均通过，无提交。尚待独立复核；未执行真实 Provider、网络、数据库、前端联调或生产 SSE 验收，因此不声称生产上线完成。

## R3：camelCase / PascalCase 敏感键规范化补强

### 变更范围与 TDD 证据

独立复核继续指出：既有敏感键规范化只处理小写和连字符，嵌套的
`modelCandidates`、`toolArgs`、`rawPage`、`HiddenReasoning` 会绕过
`_SENSITIVE_KEYS` 并进入 SSE 历史。本轮只修改
`runtime/event_hub.py` 和 `tests/runtime/test_event_hub.py`：新增四个递归
payload 测试，先运行得到 `4 failed, 15 deselected in 0.84s`，均因未抛出
`ValueError` 失败。

最小实现新增统一键名规范化：先保留既有连字符转下划线，再识别 camelCase
和 PascalCase 边界并转为 snake_case，最后小写后匹配既有敏感键集合。它只
处理结构键；普通正文中的 `token` 仍不因单词本身被拒绝，错误信息仍不回显
敏感值，原 snake_case / 连字符键仍兼容。

### GREEN、静态和架构门禁

```powershell
.venv\Scripts\python.exe -m pytest tests/runtime/test_event_hub.py -q
.venv\Scripts\python.exe -m pytest tests/runtime/test_event_hub.py tests/api/test_operation_delivery_v2_events.py tests/contracts/test_stream_event_contracts.py -q
uv run ruff check src/efficiency_platform_agent/runtime/event_hub.py tests/runtime/test_event_hub.py
uv run ruff format --check src/efficiency_platform_agent/runtime/event_hub.py tests/runtime/test_event_hub.py
uv run mypy --follow-imports=skip src/efficiency_platform_agent/runtime/event_hub.py
uv run python -m compileall -q src/efficiency_platform_agent/runtime/event_hub.py tests/runtime/test_event_hub.py
.venv\Scripts\python.exe -m pytest tests/architecture/test_dependency_rules.py -q
```

结果依次为：`19 passed in 0.39s`；`67 passed in 0.60s`；Ruff 检查通过；2 个
文件格式正确；mypy 为 `Success: no issues found in 1 source file`；compileall
退出码 0；架构守卫为 `12 passed, 47 subtests passed in 2.53s`。直接运行 mypy
并跟随全部导入时，会遇到未改动的 `providers/research/_process_isolation.py`
对 `feedparser` 缺失类型桩；该既有依赖问题不归入本次两文件的定向类型门禁。

### 全量回归阻断的系统化诊断

使用当前项目解释器执行：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

明确结果为 `1 failed, 1696 passed, 9 skipped, 2 warnings, 280 subtests passed
in 82.26s`。唯一失败为
`tests/unit/harness/test_live_acceptance.py::test_authorization_cannot_be_reused_with_a_new_request_id`。
为排除偶然性，该单测连续两次均稳定失败（分别为 `1 failed in 2.57s` 和
`1 failed in 1.32s`），其最小相关文件也稳定为 `1 failed, 8 passed in 0.83s`。

调用链为 `LiveAcceptanceService.execute` → `_execute_owned` →
`InMemoryLiveAcceptanceBudgetBinder.bind`。第二个不同 `request_id` 在
`bind` 的 `LIVE_AUTHORIZATION_REUSED` 分支立即抛错，因此不会再进入
`runner.run_case("ordinary_chat")`。该测试一面捕获“拒绝复用”，一面又断言
第二个用例已经由 runner 执行，二者与“绑定先于执行”的现有实现语义冲突。

本轮修改文件不导入、调用或提及 `LiveAcceptanceService`；本轮文件最后修改
时间为 16:58 / 16:59，而失败路径文件最后修改时间为 10:16 / 10:17。该失败
稳定、与 R3 无依赖且不应通过篡改无关测试或 Live Acceptance 逻辑掩盖，故未
在本任务修复。首次以 `uv run pytest -q` 运行时还曾误走另一工作区的 pytest
启动路径并报缺少 `dateparser`；此问题已由当前项目 `.venv` 解释器复核排除，
不作为代码失败依据。

### R3 文件快照与状态

| 文件 | SHA256 |
|---|---|
| `src/efficiency_platform_agent/runtime/event_hub.py` | `A0368E3EE20B12A2D4404945DE2D3293D8174DED8F5C3C5E5EA716038B7A03F6` |
| `tests/runtime/test_event_hub.py` | `D904E243C7523B6E77664F1AB17B751E202730BBB3C6A89E178EF2F74FE23343` |

Status：DONE_WITH_CONCERNS，R3 聚焦、Task 5 组合、静态与架构门禁通过；全量
仅被上述稳定且无关的 Live Acceptance 断言冲突阻断。Task 5 仍为**待独立复核**；
未执行 Git、网络、数据库或生产 SSE 验收。
