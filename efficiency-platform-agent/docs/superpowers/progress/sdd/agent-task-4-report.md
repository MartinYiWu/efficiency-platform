# Task 4：V2 聚合实施记录

| 属性 | 内容 |
|---|---|
| 状态 | DONE_WITH_CONCERNS；最终全量通过，兼容与计数口径见本文 |
| 负责人 | Task 4 实施 Agent |
| 适用范围 | OperationAgent 聚合、组合根版本固定与 Research V2 终态 |
| 更新时间 | 2026-09-17 |
| 关联需求 | [Task 4 brief](agent-task-4-brief.md) |

## 初始核对与首轮 RED（历史记录）

完整阅读项目 AGENTS.md、三份架构约束、Task 4 brief、TDD 技能以及冻结 V2 契约、展示组装器和模型 Specialist；确认项目不存在 `.codegraph`。

新增 `tests/integration/test_operation_deliverable_v2.py`，经真实 Supervisor 链测试默认 V2、部分结果、完成 V2 向 V1 投影、非法版本拒绝。

## RED 证据

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py -q
```

退出码 1：`4 failed in 3.20s`。默认 V2 用例返回 `deliverables=None`；另外三个用例报告组合根尚不接受 `deliverable_set_contract_version`。这是行为尚未实现的预期红灯。

## 首轮上下文请求（已由协调方裁定）

1. brief 同时要求“V1 只能对已完成 V2 集合确定性投影”和“V1 集合派生 Specialist deliverable/1”。二者在真实生成链中冲突，需要固定一种明确语义，不能根据模型返回字段猜测版本。
2. 清单外 `harness/research_v2_adapter.py` 当前丢失 Research V2 的 brief/outcome/provenance：PARTIAL 投影为 SUCCEEDED，NO_MATCHES 被投影为 FAILED。聚合器无法从现有 ResearchResult V1 恢复这些事实。
3. 清单外 `agents/operation/specialists/model_backed_research.py` 无交付版本参数，且在 `_delegate()` 内固定构造默认 V1 Specialist；需要窄改版本透传，或协调方确认受控组合根包装。
4. 清单外 `scenarios/runtime_quality.py` 将任何 payload 直接送入 V1 assembler。可在白名单 OperationAgent 内用显式 V2 到 V1 质量视图包装，但完整 V2 Research 结果仍须解决上一项。
5. Supervisor 在空结果时不创建 bundle，ScenarioPackService 又将 COMPLETE+无 bundle 转 FAILED；NO_MATCHES 必须由可信研究运行事实单独处理，不得从正文猜测。
6. brief 要求旧 V1 测试显式配置 V1，但 `tests/integration/test_operation_agent_runtime.py` 不在白名单；现有模型替身全部返回 V1，默认切 V2 后需要明确迁移其文件范围。

上述差异已向协调方报告；未通过扩大白名单、绕过中央 Supervisor、重新采集研究或让模型补事实来规避。

## 首轮暂停时的文件与验证边界（历史记录）

- 新增：`tests/integration/test_operation_deliverable_v2.py`。
- 测试文件 SHA256：`9927CDA2289342CA6139A70415162C8E9129D25FE33FEAD7374DAB15EBB99795`。
- 新增：本报告；正式账本追加本次记录。
- 生产代码未修改，新 Run 默认仍为 V1。
- 未执行 GREEN、全量测试、源码编译或静态门禁，不声称 Task 4 完成。
- 永久 non-Git：未执行任何 Git 命令，无提交。

## 协调方裁定与实施结果

协调方同步 brief 后，批准必要研究桥接、质量门、场景空集合语义、旧 V1 测试迁移和 `local_real_factory.py` 版本参数薄透传；仍禁止修改中央 Supervisor 生命周期、Research Service、冻结 V2 契约及 Task 3 模型生成器。

- `build_operation_agent()` 与 `build_local_agent_application()` 新 Run 默认 `deliverable-set/2`，显式 V1 则固定派生 `deliverable/1`，显式 V2 固定派生 `deliverable/2`。OperationAgent 的公开版本属性不可重新赋值。
- V2 payload 经严格 `DeliverableSetV2` 判别模型和 `assemble_set_v2()` 校验；V1 保持原生 V1 assembler。V2 质量门仅将已经生成的 V2 payload 单向投影为 V1 检查视图，正式 payload 不改为 V1。
- `ResearchV2ProviderAdapter.for_run()` 每次返回独立实例，共享服务但不共享结果观察器；受信任 brief/outcome 记录在该 Run 独立 OperationUsage。身份校验包含 tenant、task 和显式 run_id；不存在共享的“当前 Run”槽。
- 原有 Supervisor 仍唯一调度研究专家；研究 Service 每个研究请求只调用一次。已接纳 DeliveryPack 事件和 claim 文本确定性映射为 ranked_digest，不让模型减少条目、补事实、决定领域状态或扩大采集预算。
- COMPLETE 生成完整集合；PARTIAL 保留合格事件，OperationExecution 为 PARTIAL，集合 degraded=true，并输出 `RESEARCH_TARGET_NOT_REACHED` 与具体缺口；NO_MATCHES 仅由当前 Run 中匹配研究 request_id、tenant/task/run 身份、brief digest 的可信领域终态恢复为空集合，warning 不具备授权能力；FAILED 没有伪交付。
- 质量报告 WARNING/UNKNOWN 产生结构化 `QUALITY_REPORT_WARNING`，一般专家部分失败保留合格平台并输出具体缺失范围。
- Run 输出增加 `delivery_contract_version`；V2 `content` 取 `summary.message`，V1 保持字符串 summary；未新增 SSE 事件。

## 兼容矩阵与 provenance 口径

| Run 集合版本 | 研究来源 | 结果 |
|---|---|---|
| 默认 V2 | ResearchV2ProviderAdapter | 保留终态、冻结时间窗、排序口径、事件和证据；离线端到端通过 |
| 显式 V1 | 旧 ResearchProvider | 原生 V1 Specialist 与 V1 assembler；既有预期语义保留 |
| 默认 V2 | 旧 ResearchProvider；行业摘要或 requires_research 多平台任务 | 组合根未声明 governed Research V2 能力时，在启动 Supervisor 前失败 `RESEARCH_UNAVAILABLE`；研究与内容模型调用均为 0 |
| V2 | 当前 Run 匹配的 Research V2 NO_MATCHES 领域结果 | 行业摘要恢复成功空交付，来源计数为 0；冻结时间窗完整保留，内容模型调用为 0 |
| V2 | 只有 EMPTY/warning，或研究事实 request/run 不匹配 | 失败关闭，无空集合交付；不能以 `RESEARCH_NO_MATCHES` warning 绕过可信研究结果 |

回退入口：在 `build_local_agent_application()` 或 `build_operation_agent()` 显式传 `deliverable_set_contract_version="deliverable-set/1"`。不得根据模型 payload 字段或有无 body 自动选版本。

来源数是已交付事件中唯一来源 URL 数；时间窗和排序直接取冻结 ResearchBrief。引用保守标记为 unverified，verified_source_count=0，不把研究可用性等同于外部事实核验。现有 ResearchOutcome 不提供全量采集候选/淘汰计数，因此 candidate_count、merged_event_count、retained_count 仅表示本次已接纳交付集合大小，eliminated_count=0 仅表示该集合中未再淘汰；不代表上游全量采集漏斗计数。该口径已获协调方确认。

## 后续 RED → GREEN 证据

1. 加入 Research V2 四终态与 adapter 的 PARTIAL/EMPTY 测试：`9 failed, 5 passed in 3.16s`。实施后同一两文件命令 `14 passed in 1.96s`。
2. 新增质量 WARNING 降级回归：`1 failed, 10 passed in 2.61s`，证明 V2 丢失既有质量 warning；修复后新测试通过。
3. 本地工厂显式版本透传回归：`1 failed, 11 passed in 3.83s`，实际捕获版本为 None；补透传后通过。
4. V2 非空旧研究端口失败关闭回归：`1 failed, 12 deselected in 2.19s`，原路径调用模型并返回泛化失败；补提前拒绝后，目标集成、既有运行链和研究会话三文件 `46 passed in 3.16s`。

主要命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py tests/unit/harness/test_research_v2_provider_adapter.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py tests/integration/test_operation_agent_runtime.py tests/acceptance/test_operation_supervisor.py tests/acceptance/test_research_v2_closed_loop.py tests/orchestration/research_v2/test_planner.py tests/orchestration/research_v2/test_termination.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py tests/unit/harness/test_research_v2_provider_adapter.py tests/architecture/test_dependency_rules.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py -k without_governed -q
```

指定主链/有限补采组合为 `59 passed in 5.59s`；V2/adapter/AST 组合为 `30 passed, 47 subtests passed in 5.93s`。并发回归在同一个共享 adapter/service 上并发运行两个不同 Run，分别得到 PARTIAL/NO_MATCHES、1/0 来源数及各自冻结时间窗；共享 adapter 的 result_observer 仍为 None。

首次全量 `.venv\Scripts\python.exe -m pytest -q`：`1649 passed, 9 skipped, 2 warnings, 280 subtests passed in 60.18s`。该次在最后的旧 Provider 提前失败关闭修改之前；最终结果将追加到本报告。

## 静态门禁与限制

对下列 9 个修改生产文件执行 `.venv\Scripts\python.exe -m mypy`：`Success: no issues found in 9 source files`。对下列 15 个 Python 文件执行 Ruff check 与 format --check：`All checks passed!`、`15 files already formatted`。`.venv\Scripts\python.exe -m compileall -q src tests` 退出码 0。

扩大到旧测试依赖链的 mypy 未通过：生产与测试联合调用暴露 65 项问题，包括既有测试替身协议、旧测试 optional 缩窄和其他测试模块类型错误；其中本次新增的会话输出 `plain()` 类型错误已改为直接判定 JSON dict。单独对测试路径运行还会触发项目缺失 py.typed/import-untyped 问题。未修改无关测试或放宽 mypy 配置，不声称测试依赖链类型检查通过。真实 Provider、网络、数据库、生产持久化与上线验收未执行。

## 最终修改文件快照清单

| 文件 | SHA256 |
|---|---|
| `src/efficiency_platform_agent/agents/operation/execution.py` | `7A8A857B5773B1D2D602D35004B8F46C74E7B0C19AD908F116E0768D5155C1D6` |
| `src/efficiency_platform_agent/agents/operation/operation_agent.py` | `25E4544FF47CC59910DC56F0E3C8DAD671424A4F595189DF028435F689D675C5` |
| `src/efficiency_platform_agent/harness/operation_agent_factory.py` | `D8AA04A5F4B200EED0398C1365A320CFE18FD02465A9A6EE838B527680DE4C26` |
| `src/efficiency_platform_agent/harness/research_v2_adapter.py` | `AB1DEC14C5337BC67322E4A3B026663E1440E376F69581DA7B87AF84AF47CCE3` |
| `src/efficiency_platform_agent/harness/local_real_factory.py` | `EB4DB1CE4684A7F2449FFE25B359FD1526231CB2CFE44C49E7F001B25919D39E` |
| `src/efficiency_platform_agent/agents/operation/specialists/model_backed_research.py` | `0354928EDF0D13C50279CD827387D561BB32299A5B857AB65E303D47553859DB` |
| `src/efficiency_platform_agent/agents/operation/scenarios/runtime_quality.py` | `40E3637ADDD79A6AA93ECAF4AE1AA9BB09877DE0009B488746CF148BACC60BAB` |
| `src/efficiency_platform_agent/agents/operation/scenarios/service.py` | `5491B9A106AEF47E0826DF9F7C97E94CB8A0A67E363A68D43096D01A8DB7957B` |
| `src/efficiency_platform_agent/orchestration/builders/operation_runtime.py` | `D2FA42779804826926EFD7C71B1EBBAB47DE0EDE93A25C6F3203A51A4613D2A0` |
| `tests/integration/test_operation_deliverable_v2.py` | `050B699764497630015923FDEAA64F5DD779ACD2D194D6D6372878F89748E850` |
| `tests/integration/test_operation_agent_runtime.py` | `8D8E9765C04B1B3A5B1090E953CB21A598E7ABAE4BBC8E0374145D59DF91E7BD` |
| `tests/acceptance/test_research_backed_multi_platform.py` | `B0E5CF55EA3C8AAF8BC360FA876E45B4D5AC919108C46CCE442F2AA487AD8648` |
| `tests/acceptance/test_research_v2_closed_loop.py` | `B1655F7D07C5910EE3D23C00C969C38D488937B22D7AFECDAA47A43423E4F67B` |
| `tests/unit/harness/test_research_v2_provider_adapter.py` | `79D5CBAB3558C03786FCE849F3CDEF147F6860775CBC3449543E07696E795698` |
| `tests/unit/harness/test_local_real_factory.py` | `1BD364C2527DC232A2D251B806318E2FAB31F1D9EF3E501CC1F29F740AAE6B78` |

另修改本报告与正式进度账本。未修改虽获授权但不需要变更的 scenarios 对应单元测试文件；实际新增行为由真实 Supervisor 集成覆盖。所有源文件均在最终批准白名单内，永久 non-Git，无提交。

## 最终全量与交付状态

最后一次生产修改后的完整命令：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

退出码 0：`1650 passed, 9 skipped, 2 warnings, 280 subtests passed in 54.68s`。两条 warning 仍为 Starlette alias deprecation 与 Polars Excel future behavior。

Task 4 实现完成，Status：DONE_WITH_CONCERNS。担忧为已裁定的 V2/旧研究端口兼容矩阵、已交付集合计数而非全量采集漏斗的 provenance 口径，以及扩大后的旧测试依赖链 mypy 未通过；生产修改的 9 文件 mypy、15 文件 Ruff、源码编译、AST 和全量运行测试均通过。不包含真实服务/生产验收，无提交。

## 独立审查修复：统一研究准入与可信空结果恢复

独立审查发现两个 Important：旧 ResearchProvider 可由 requires_research 多平台路径绕过 provenance 准入；NO_MATCHES 仅凭 warning 即可授权空 V2。先补真实 Supervisor 回归，未降低既有断言。

RED：

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py -k 'platforms_require_governed or warning_cannot_authorize' -q
```

退出码 1：`4 failed, 13 deselected in 3.66s`。多平台任务实际为 COMPLETE；warning-only 的 absent、wrong-run、wrong-request 三种情况也都返回 COMPLETE。

修复：组合根根据明确装配的受治理适配器注入 `governed_research_v2` 能力标记；OperationAgent 不检查 Provider 类名或猜测字段，在进入 Supervisor 前统一检查研究任务准入。V1 路径不受影响。ScenarioPackService 恢复所有 COMPLETE+无 bundle 的原始失败规则。适配器将本次 request_id 连同 brief/outcome 记录到每 Run 独立 OperationUsage；OperationAgent 仅将 `SCENARIO_BUNDLE_INCOMPLETE` 在当前研究 request_id、tenant/task/run 身份、brief digest、NO_MATCHES 与空事件一致时恢复为 COMPLETE，不覆盖取消、其他失败或质量门错误。

GREEN：

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py -q
.venv\Scripts\python.exe -m pytest tests/integration/test_operation_deliverable_v2.py tests/integration/test_operation_agent_runtime.py tests/acceptance/test_operation_supervisor.py tests/acceptance/test_research_v2_closed_loop.py tests/orchestration/research_v2/test_planner.py tests/orchestration/research_v2/test_termination.py tests/unit/harness/test_research_v2_provider_adapter.py -q
```

分别为 `17 passed in 3.51s`、`74 passed in 7.82s`。合法 adapter NO_MATCHES 仍成功且内容模型调用为 0；旧研究端口的多平台请求在研究和内容模型调用前失败，二者调用均为 0。warning-only Specialist 确实经过中央 Supervisor 后被拒绝，避免只靠提前准入掩盖第二项问题。

修复后 9 生产文件 mypy 再次通过；15 文件 Ruff/format、compileall 再次通过；AST 为 `12 passed, 47 subtests passed in 2.04s`。本轮仅修改原白名单中的 5 个生产文件、已有 Task 4 集成测试、本报告及账本。上方 SHA256 表已更新。

修复后的最终全量命令 `.venv\Scripts\python.exe -m pytest -q`：退出码 0，`1654 passed, 9 skipped, 2 warnings, 280 subtests passed in 64.90s`。两项 Important 的实施修复完成，等待独立复审；无提交。前述 1650 项为审查修复前历史证据，以本段 1654 项为本轮最新全量证据。
