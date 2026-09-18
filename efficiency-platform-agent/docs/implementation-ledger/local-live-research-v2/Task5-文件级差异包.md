# Task 5 正式阶段执行器与模型决策差异包

状态：独立复核 I1～I3 已修复并离线验证，待重新复核；负责人：Agent 端维护负责人；更新时间：2026-09-17。
适用范围：本地实时研究 Task 5；关联：[实施计划](../../superpowers/plans/2026-09-17-免费公开源本地实时V2研究闭环-实施计划.md)。

## 文件白名单与变更前基线

- 新增 `src/efficiency_platform_agent/orchestration/research_v2/stage_runner.py`。
- 新增 `src/efficiency_platform_agent/capabilities/research/v2/model_decisions.py`。
- 修改 `src/efficiency_platform_agent/orchestration/research_v2/graph.py`，只增加阶段预算版本及部分交付路由。
- 新增 `tests/orchestration/research_v2/test_live_stage_runner.py`。
- 新增 `tests/unit/capabilities/research_v2/test_model_decisions.py`。
- 新增本差异包，主进度账本只追加 Task 5 记录。

原文件快照位于 `task5-before/`；四个源码/测试新增文件在任务开始时不存在。
`state.py`、`planner.py` 仅保存快照，没有修改；Task 3 store、Task 4 工具/获取器、公共预算与模型基础设施没有修改。

| 基线快照 | SHA-256 |
|---|---|
| `graph.py.snapshot` | `4B5BD3C62DB337482B1718EE146D2FF17D0271D2544B518459924690E7D2104F` |
| `state.py.snapshot` | `0DB4CFABE7EF493F6FC8B8338F03772529C8C19AF02D78BF7170BE74658D9D4D` |
| `planner.py.snapshot` | `2120D68B06F399A75F3F9AEACC3A264ACDCB32E0738F837AEAE457A593CE3325` |
| `2026-09-17-免费公开源本地实时V2研究闭环-进度账本.md.snapshot` | `2F7AD02E83C3FD18484FF290F121F7272FE0B87920F7B104051D5BCDB5024726` |

## 实现与组合接口

`LocalLiveResearchStageRunner` 实现既有 `run_stage(stage, state)` 协议。构造时注入同一可信 key/store/Brief、policy、binding、registry/source_context、AcquisitionExecutor、ResearchContentAcquirer、AcquisitionContext、ResearchModelDecisions 及 `output_stages`。没有自行创建 ToolRuntime、网络限流器或研究循环。

- validate 检查 tenant/run/task/revision、Brief digest/version、lease、预算版本、活动 facts；同一 Acquirer/Executor Runtime、模型 binding 与可信运行身份必须一致。取消信号、硬截止和既有终态在阶段前后复核，CAS 保存沿用 Task 3 store。
- plan 以登记且当前允许的来源、原 Brief 和质量缺口生成服务器端固定候选动作；模型仅选择已生成 action ID，ActionValidator 再验证。发现经 AcquisitionExecutor，正文只经 Task 4 Acquirer；前序 ID 必须能解析到当前 facts，不接受模型补出正文或 URL。
- normalize/filter/deduplicate/cluster/claims/quality 复用既有组件。Graph state 只保存 ID 和控制字段，正文、证据、事件、主张和计划均在 Run facts store。来源失败记录追加保留，后续成功不覆盖早期失败。
- summary 只有通过 Acquirer 独立获准端点重新取得正文后，才以受控成功获取标识赋予新 normalized document 的 full scope；原始 candidate 摘要及 scope 原样保留，不能直接升级摘要。metadata_only 与 platform_text 的权限边界仍由 Task 4 约束。
- 发布日期优先使用提取器的实际发布时间；RSS 的 `raw_published` 仅在明确时区且可解析时用 RFC 5322 兼容解析补充。ISO 已有路径不变；绝不使用 `updated` 或推测日期替代发布时间。
- Model adapters 通过统一 ModelRuntime、ContextBuilder、已注册 PromptRuntime 发起受预算约束的 JSON 候选；当前父预算剩余量扣除输出保留后约束研究阶段。程序逐一验证 schema、已知 action/document/event/evidence ID、Brief/prompt/hash、正文片段、quote 范围与数字。模型新增 URL、未知 ID、标题冒充正文、伪造引用范围均被拒绝；聚类和 ClaimExtractor 保留确定性验证。
- 资源统计仅累计同一 Run 不可变 audit_records 中 invocation_id 以 `research-http-` 开头的实际结算。`bound-http` 是调用瞬间名称，不能用于持久化记录过滤。保留公共计费链中的外层 Tool + 内层 HTTP 双计数；回归明确两个实际 HTTP 对应父账本四次调用，不将 Tool 调用误记为 HTTP。正文 attempt 的 requests/bytes 也取该审计增量；Run 全局正文获取限制为 30。
- NO_MATCHES 必须满足计划全部完成、发现成功且完整、无未获取候选/不确定过滤、来源历史已核验；否则保留质量缺口。
- 达到补采轮次或软/预算边界时，有合格事件可走 compose→verify→render；不得重启补采。保存最后已验证的 qualified_events/claims/evidence 闭环，以便后续预算不足时保留部分结果。取消和硬截止仍直接终态。
- compose/verify/render 仅委托既有 `ResearchStageRunner` 协议的 `output_stages`，并限制返回值不得新增研究事实 ID。本任务没有实现 Task 6 的 Materializer 或真正输出内容。

## TDD 红绿证据

每轮先补测试再改实现；全部使用离线连接器/DNS/模型替身。一个模型预算用例调用正式 ModelRuntime 配合既有离线 FakeModelProvider，源码无 Fake/fixture import。

| 回归批次 | RED（退出码 1） | GREEN（退出码 0） |
|---|---|---|
| 指定两测试文件的首次执行 | `17 failed in 4.33s`，正式模块缺失及部分交付出口不通 | `17 passed in 2.26s` |
| 正式阶段链、精确数量、原始发布时间与预算 | `4 failed, 22 passed in 5.50s` | `26 passed in 6.24s` |
| NO_MATCHES、内容和取消边界 | `2 failed, 28 passed in 7.04s` | `30 passed in 5.74s` |
| 模型嵌入 URL、提取空正文 | `2 failed, 35 passed in 7.14s` | 后续完整聚焦集合通过 |
| 软截止与预算停止不得新补采 | `2 failed, 22 passed in 6.79s` | `39 passed in 6.53s` |
| 正文失败/后续成功 attempt 必须记录真实 HTTP 用量 | `1 failed in 2.69s`，预期 `[1, 1]` 实为 `[0, 0]` | `1 passed in 2.01s` |

精确数量回归走正式研究阶段并验证要求 5 条、实际只有 3 条时有限补采、原时间窗不变且终态 PARTIAL；输出阶段采用协议替身，因此此处不表示 Task 6 内容验收完成。同事件转载仍只计一个独立源。

## 最终验证命令与结果

以下均在项目根执行，没有启动服务或访问真实网络/模型。

```powershell
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2/test_live_stage_runner.py tests/unit/capabilities/research_v2/test_model_decisions.py -q
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2 tests/unit/capabilities/research_v2 tests/architecture tests/unit/harness/test_research_local_tools.py -q --tb=short
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent
.venv\Scripts\python.exe -m compileall -q src tests scripts
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/orchestration/research_v2/graph.py src/efficiency_platform_agent/orchestration/research_v2/stage_runner.py src/efficiency_platform_agent/capabilities/research/v2/model_decisions.py tests/orchestration/research_v2/test_live_stage_runner.py tests/unit/capabilities/research_v2/test_model_decisions.py
```

依次结果：`39 passed in 6.56s`；`256 passed, 124 subtests passed in 16.68s`；`All checks passed!`；`Success: no issues found in 302 source files`；退出码 0 无输出；`5 files already formatted`。最后新增长断言曾触发格式检查 1 文件不合规，限定该测试文件自动格式化后已通过，不涉及逻辑变更。

格式化后指定聚焦复验：`39 passed in 7.50s`。文档写入后执行 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short`，得到 `20 passed, 122 subtests passed in 4.68s`，退出码 0。

验证后 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `orchestration/research_v2/graph.py` | `36C71BD427F688B05169387B47E0DA0161418A4232B480D386218A6C6AAD5C58` |
| `orchestration/research_v2/stage_runner.py` | `5F09F9BA803B84DB3B37575C947CA6FC8299CD488219819D726891027A9247CD` |
| `capabilities/research/v2/model_decisions.py` | `9E90AEC55761A3DC0C69501419BC4264C4B748D69384599DFF01D7DD321DE943` |
| `tests/orchestration/research_v2/test_live_stage_runner.py` | `E9431DA3C37E9DA43EF5528B0682CA5A062E0B00A073C72AE5755F3890A9F9F8` |
| `tests/unit/capabilities/research_v2/test_model_decisions.py` | `53D1530CEAE30FC8BFD1E88BCE231A46919D2A3FAFD170FDCD89D14904E40EA5` |

## 后续约束与未完成项

- Task 6 的正式 Materializer/output_stages 必须读取同一可信 store/key/identity，并保持父预算、输出保留、取消和硬截止；不能创建新研究事实或在有限部分交付出口重启补采。
- Task 7 负责应用级唯一 `LocalResearchNetworkLimits()`，为每 Run 构造共用该限流实例的 Task 4 工具与取消适配。必须继续注入原绑定对象及同一 Runtime，不能在阶段执行器内新建预算或独立限流。
- 当前来源配置仍全部禁用，没有新增真实端点/正文许可，没有将离线 descriptor 当作真实准入证据。
- 尚待独立规格/代码复核；Task 6～9、真实两轮会话和 production 就绪不由本任务证明。未读 `.env`、未执行 Git、未联网或调用真实模型、未启停服务、未改 UI/Java/DB/部署。

## 独立复核 I1～I3 修复记录

以下记录替代前文对应的首次实现行为；本轮原始独立复核为 FAIL，当前为修复后待重新复核，不声称评审已经通过。

### I1：正文配额按每次真实 HTTP 派发执行

复现：16 个获准正文候选各经过两跳，原 StageRunner 和 Task 4 fetcher 都按一次 acquire/fetch 计数，实际连接器收到了 32 次请求。新增正式 ToolRuntime 与 StageRunner 两条回归，均先断言 30 次上限；RED 为 `2 failed in 2.61s`，退出码 1（`32 == 30` 不成立）。

经确认的必要白名单扩展：`harness/research_local_tools.py`、`providers/research/transport.py` 和 `tests/unit/harness/test_research_local_tools.py`。没有改公共 Tool Runtime 生命周期或父预算计费规则。

- `FetchLease.dispatch_quota` 新增可选中立 `HttpDispatchQuota` 端口；逐跳 `_request_with_budget` 先预约派发许可，再预约既有父预算。父预算失败或取消时释放许可；仅在调用 connector 的紧前同步提交许可，派发后不可退回。配额不足在 HTTP 预算预约及 socket 之前失败关闭。
- Task 4 工厂可注入 `LocalResearchBodyHttpQuota(binding)`；不显式注入时，为该工厂创建的可信 Run Runtime 生成一个实例。该 Run 的所有正文 fetcher 共用它，来源切换不能重置配额；发现 fetcher 不注入。注入的 quota 必须是同一个 binding 对象，预约时也校验当前绑定。Task 7 若因合法组合需要重新建立同 Run 工具，必须保留并复用该 quota，不得刷新配额。
- 配额同步维护已派发与未派发预约总数，上限 30；StageRunner 统计改为真实 `research-http-` 审计 calls 增量，不再每次 acquire 简单加一。外层 Tool + HTTP 父账本双计数保持不变。
- 正式工具断言：第 16 个两跳候选被拒绝，连接器恰好 30 次，HTTP audit 恰好 30 次、105 字节，父账本 46 次（16 Tool + 30 HTTP）；切换至同 Run 的 HN 正文来源仍不能打开第 31 个 socket。StageRunner 同样只记录 30 次正文实际请求。
- 补强回归：父预算预约连续失败或取消 31 次，正文已派发数仍为 0、审计与 socket 均为 0，恢复后可派发一次；正文配额耗尽时 discovery 仍可调用且不改变正文计数。

首次 GREEN 为 `2 passed in 2.25s`；补强命令 `.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_tools.py -k 'body_http_quota or body_permit' -q --tb=short` 为 `4 passed, 34 deselected in 2.74s`。中途修正了新测试对既有 `invoke` 二元返回值与安全错误投影的断言访问，没有修改生产错误投影以迁就测试。

I1 原始红绿使用命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_tools.py::test_body_http_quota_counts_each_redirect_before_socket_dispatch tests/orchestration/research_v2/test_live_stage_runner.py::test_acquire_reports_actual_redirect_http_body_requests -q --tb=short
```

### I2：聚类提案所有字符串字段中的 URL 失败关闭

模型成员 ID 合法不能证明 event_type/entity_names/merge_basis 等附加字符串可信。适配器在 schema 解析后检查整个 proposal 的字符串序列化，拒绝显式协议 URL、协议相对 URL 和 `www.` URL；不接受模型创造这些字段里的链接。已有 schema、成员 ID 和 EventClusterer 确定性裁决仍保留，普通事件类型、实体与产品版本不受影响。

回归覆盖 event_type、product_version、entity_names、merge_basis、proposal_id 五字段与 HTTPS/FTP/协议相对三类 URL；命令 `.venv\Scripts\python.exe -m pytest tests/unit/capabilities/research_v2/test_model_decisions.py -k every_string_field -q --tb=short`，RED 为 `15 failed, 15 deselected in 3.20s`（未抛出），GREEN 为 `15 passed, 15 deselected in 2.01s`。

### I3：输出端不得撤销采集停止状态

调用 compose/verify/render 前保存已生效的 budget_exhausted、soft_deadline_reached、cancelled、hard_deadline_reached、fatal_error；合法输出 patch 可以补充交付信息或增加停止状态，但不能以 false/None 撤销之前的 true。停止后 verify 即使要求 recollect，Graph 也不再回 plan。

回归先使用正式 plan→discover→acquire→normalize→filter→deduplicate→cluster→claims→quality 得到真实部分事件与硬缺口，再分别置预算/软截止停止，并注入明确返回 false 或 None 且请求 recollect 的输出协议实现。断言停止标记保持 true、后续 Graph 仅走 validate→plan（只检查停止）→compose→verify→finalize、没有新增 HTTP、终态 PARTIAL。

命令 `.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2/test_live_stage_runner.py -k cannot_reopen -q --tb=short`，RED 为 `4 failed, 25 deselected in 5.86s`，GREEN 为 `4 passed, 25 deselected in 5.25s`。

### 修复后完整门禁

```powershell
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2 tests/unit/capabilities/research_v2 tests/unit/harness/test_research_local_tools.py tests/contract/providers/research_v2 tests/architecture -q --tb=short
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2/test_live_stage_runner.py tests/unit/capabilities/research_v2/test_model_decisions.py -q
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent
.venv\Scripts\python.exe -m compileall -q src tests scripts
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/providers/research/transport.py src/efficiency_platform_agent/orchestration/research_v2/stage_runner.py src/efficiency_platform_agent/capabilities/research/v2/model_decisions.py tests/unit/harness/test_research_local_tools.py tests/orchestration/research_v2/test_live_stage_runner.py tests/unit/capabilities/research_v2/test_model_decisions.py
```

完整组合门禁 `355 passed, 124 subtests passed in 31.43s`；指定两文件聚焦 `59 passed in 9.96s`；Ruff `All checks passed!`；mypy `Success: no issues found in 302 source files`；compileall 退出码 0 无输出；格式检查 `7 files already formatted`。所有请求/模型均为离线替身；没有真实网络、模型、服务或其他范围外操作。

修复文档写入后的 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short` 为 `20 passed, 122 subtests passed in 3.87s`，退出码 0。

修复前逐字快照位于 `task5-review-before/`，文件名为下表 basename 加 `.snapshot`。前四个 Task 5 原文件的基线见前表；必要扩展三文件的修复前 SHA-256 分别为：research_local_tools `BF7EE6A0C758B6D58D29B63C597C8F9DFB5A55D7DD37B3451BB53826CE87FFF9`，transport `3492215D4ED3DA0DBBBFE36E9FD152A315B8CBD72B6445368643464B4A8F4ACC`，工具测试 `A33378A05ECA69DE0EA629F1F2B3E645056602CC6B1A2492F5B08E7998A996E4`。

| 修复后文件 | SHA-256 |
|---|---|
| `harness/research_local_tools.py` | `44E26EC03C94294A5238F20898D013F93C154079D0377A92F166B3E9BBC7B843` |
| `providers/research/transport.py` | `6291D8C3D1055D2C895219305354E0AF265365A1681318ECD74E02684C2C860C` |
| `orchestration/research_v2/stage_runner.py` | `3B6F8D59C3725A0E722EEE95C07A47E0DFEC3AD9F01966F8DFC518964EEED7CF` |
| `capabilities/research/v2/model_decisions.py` | `83EEC2A5BB4AD9427F714D1675231A8CCAFC56BBC191E72940D003589C585BE0` |
| `tests/orchestration/research_v2/test_live_stage_runner.py` | `172BADC2D8849A84A9ED50893850A66AF8C6A8A1B72F569D3C06A786D55D86FA` |
| `tests/unit/capabilities/research_v2/test_model_decisions.py` | `89DA1F316E50C817A394A84762B37ABB8A0E26D44886A4D5C7442DA0CD9304B2` |
| `tests/unit/harness/test_research_local_tools.py` | `4C6C8BDDC4177AF40D3A40C0381854894C6B3374309D646B474A54A97CF1E394` |

## I2 第二次复核：URL authority 与自然文本边界

状态：第二次独立复核发现 I2 仍 FAIL，本轮最小修复后待重新复核；更新时间：2026-09-17。仅修改 `model_decisions.py` 与其既有测试，以及本差异包/账本；不改 I1、I3 或其他运行组件。

根因：前次正则对整个 JSON 查找 `//[a-z0-9]`，既漏掉 IPv6 方括号和 Unicode authority，又把自然语言中的 `x//2` 误判。现在递归遍历实际模型字符串字段；字符串内部只提取显式 scheme URL 候选，协议相对候选仅从该字段去除前导空白后的开头识别，然后用标准 `urllib.parse.urlsplit` 解析 authority/hostname，不再使用 ASCII authority 字符类。保留 `www.` 和绝对 file URL 的保守拒绝；明显 URL 形式但解析非法时也失败关闭。

来源策略：聚类模型字段不需要 URL，因此所有检测到的 URL 均拒绝，包括已存在于输入文档的来源 URL；可信 canonical_url 保留在原文档，不由模型复制到 event_type、entity_names 或 merge_basis。普通 `Python x//2 uses floor division` 不会当成 URL，也不会被悄悄降级为 singleton，而会通过正式 EventClusterer 形成 confirmed 事件。

新增正式 Adapter→EventClusterer 参数化回归覆盖五个字符串字段与 HTTPS、IPv6 协议相对地址、Unicode IDN、带前导空白的 IDN、既有来源 URL、自然除法文本，共 30 项。

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/capabilities/research_v2/test_model_decisions.py -k distinguishes_url_authority -q --tb=short
```

RED：`20 failed, 10 passed, 30 deselected in 3.16s`，其中 15 项地址漏检、5 项自然文本误拒；GREEN：`30 passed, 30 deselected in 2.24s`。原有 HTTPS/FTP/ASCII 协议相对地址与已知文档 ID 校验继续保留。

本轮新鲜验证：

```powershell
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2/test_live_stage_runner.py tests/unit/capabilities/research_v2/test_model_decisions.py -q
.venv\Scripts\python.exe -m pytest tests/orchestration/research_v2 tests/unit/capabilities/research_v2 tests/unit/harness/test_research_local_tools.py tests/contract/providers/research_v2 tests/architecture -q --tb=short
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent
.venv\Scripts\python.exe -m compileall -q src tests scripts
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/capabilities/research/v2/model_decisions.py tests/unit/capabilities/research_v2/test_model_decisions.py
```

依次：`89 passed in 10.40s`；`385 passed, 124 subtests passed in 32.41s`；`All checks passed!`；`Success: no issues found in 302 source files`；退出码 0 无输出；`2 files already formatted`。全部退出码 0，无真实网络/模型调用及服务或范围外操作。

修复前快照 `task5-i2-recheck-before/model_decisions.py.snapshot` 和 `test_model_decisions.py.snapshot` 的 SHA-256 分别为 `83EEC2A5BB4AD9427F714D1675231A8CCAFC56BBC191E72940D003589C585BE0`、`89DA1F316E50C817A394A84762B37ABB8A0E26D44886A4D5C7442DA0CD9304B2`。修复后分别为 `9D8F8472BE5DB9067F37E4F4E868B47630307FED12DD2F5E7A9F41A2F8CEF946`、`8B1F41FD9E3C278CFD74E7C2D7109A826A21274845A352719ACA7A4BE91F5D81`。

本轮文档写入后 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short`：`20 passed, 122 subtests passed in 4.18s`，退出码 0。
