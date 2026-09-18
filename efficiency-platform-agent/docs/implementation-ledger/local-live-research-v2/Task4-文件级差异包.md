# Task 4 受控工具和内容获取差异包

状态：独立复核四项已修复并通过离线验证，待重新复核；负责人：Agent 端维护负责人；更新时间：2026-09-17。
适用范围：本地实时研究 Task 4；关联：[实施计划](../../superpowers/plans/2026-09-17-免费公开源本地实时V2研究闭环-实施计划.md)。

## 文件白名单与变更前基线

下列文件在开始实施时不存在，全部为本任务新增，无既有内容需要覆盖。

- `src/efficiency_platform_agent/harness/research_local_tools.py`
- `src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py`
- `tests/unit/harness/test_research_local_tools.py`
- `tests/unit/capabilities/research_v2/test_content_acquisition.py`
- 本差异包。

既有 Tool Runtime、Provider 与 transport 全部复用，没有修改这些文件。
主进度账本只追加本任务记录；追加前逐字快照位于 `task4-before/进度账本.md.snapshot`。
该快照 SHA-256 为 `346A0B2CC7B6D87ECF9C3469C29A606B90B7E201B4D37A054710812A601C7520`。

## 文件级变化与接口

- `build_local_research_tools(*, descriptors, binding, run_context, network_limits, connector=None, resolver=None, cancellation_signal=None, now=...) -> ToolRuntime` 显式注册四类 Provider 和 fetcher，复用 `research_tool_entries`。共享限流为必传参数，遗漏或显式 None 均拒绝。静态 host/endpoint 来自 descriptor；可信 ScopeResolver 检查 tenant/run/user 与当前 binding 对象，来源权限和证据时效逐次复核。没有 ContextVar binding 就失败关闭。
- `LocalResearchNetworkLimits` 是组合根持有的可跨 Run 共享实例：按已登记 source_id/host 保存速率窗口，按 host 单并发，总并发为 4。状态只含静态标识、锁和时间戳。跨 Run 改变同一来源限流策略失败关闭，不能借重新注册刷新配额。
- `_GovernedTransport` 复用 `SafeHttpTransport`，仅在每一跳 `_request_with_budget` 前取得共享限流槽并复核取消。等待后才由父 transport 预约/派发预算，解决“等配额时 Run 已取消却仍打开下一个连接”的竞争。原有逐跳 URL/DNS/IP 固定/Host TLS/压缩上限全部保留。
- 每个 HTTP 子请求独立预约/结算同一 Run 父账本；Tool Runtime 的外层调用计数同时保留，免费 HTTP 不借用模型费用语义。网络没有内部重试；发现重试沿用 AcquisitionExecutor，fetch 为单次受控调用。
- 原文限额收紧到 1 MiB，保证 base64/JSON 放大后仍低于既有 2 MiB Tool 限额；超限稳定拒绝，不截断成全文。主预算最多 60 调用，正文 fetch 还具有每来源 30 次上限，外层 Tool 与 HTTP 双计数使 Run 内实际正文请求不超过 30。
- `ResearchContentAcquirer.acquire(candidate, context)` 只调用 `research.fetch.v2`，显式完整参数 Schema，取得结果后再校验关联 ID。发现摘要本身不作为正文；具备独立 `article_body` 准入且精确 URL 已登记时，summary 候选忽略 inline 摘要并重新获取原文。普通 `research` 用途不推导正文许可，必须有准入记录中的 `article_body` 或 `platform_text`。
- 文章证据必须重新读取 descriptor `content_endpoints` 精确登记 URL 的 HTML/plain 原文，路径和有序查询串逐字匹配，XML/JSON 发现载荷不能升全文。HN 平台文本同样必须登记精确 item API URL，检查返回 ID/删除状态后仅提取该 item text；返回版本标记 `platform_text`，不能声明外链文章事实。非法 JSON/编码统一拒绝为 `SOURCE_SCHEMA_INVALID`，异常不携带原始 JSON 异常链。当前不启用 GitHub Release 平台正文，现有 Feed 仍保留摘要语义。
- metadata_only 来源发现输出移除正文；未经 platform_text/article_body 明确授权的对应 inline 内容不进入事实库。没有正文缓存，没有日志/事件写原文，解析库只收到内存字节。

## TDD 红绿证据

1. 首轮：先新增 28 项用例，`28 failed in 2.87s`，均断言正式组合模块缺失；完成组合及内容能力后 `28 passed in 4.38s`。实现过程中发现 Tool Runtime 要求所有可选字段显式给值，调用补齐 `etag/last_modified/cursor=None`，未放宽公共 Runtime。
2. 内容语义补强：`3 failed, 29 passed in 4.94s`，发现 HN metadata_only 仍暴露 text，以及 XML/JSON 可被当文章提取；修正后聚焦与计划契约集合 `70 passed in 4.02s`。
3. 跨 Run 配额：两个并发 Run 与取消隔离用例先得到 `2 failed, 21 deselected in 2.29s`，原因 `SHARED_SOURCE_RATE_LIMIT_MISSING`；增加共享限流后新增集合 `34 passed in 5.04s`。
4. 取消竞争：`1 failed, 23 deselected in 3.31s`，证实预算终态发生在限流等待中仍有新 socket 调用；将限流前移至预算预约/派发前后，新增集合 `35 passed in 6.07s`。

## 首次实现验证命令与结果（复核前历史）

在项目根目录执行：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py tests/unit/capabilities/research_v2/test_acquisition.py tests/contract/providers/research_v2 tests/architecture -q --tb=short
```

结果：`174 passed, 124 subtests passed in 19.30s`，退出码 0。包含计划要求的 transport、live_connector 和 research_v2_boundaries，以及完整研究 Provider 契约、发现执行器和全部架构测试。

```powershell
.venv\Scripts\python.exe -m mypy --follow-imports=silent src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py
.venv\Scripts\python.exe -m ruff check src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
.venv\Scripts\python.exe -m compileall -q src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
```

分别为：`Success: no issues found in 2 source files`、`All checks passed!`、`4 files already formatted`、退出码 0。没有宣称全仓 mypy 或全量 pytest 已完成。

文档更新后的 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short`：`20 passed, 122 subtests passed in 4.32s`，退出码 0。

验证后 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `src/efficiency_platform_agent/harness/research_local_tools.py` | `594E301028EE793AA38A94D27D1A91AB68377EFA7DE9DF2AC00258ABBC1D4214` |
| `src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py` | `42F520B58E224B048B77513B5F50407BC3EFE136C5C6E662F621672B6E178F78` |
| `tests/unit/harness/test_research_local_tools.py` | `EC5186CC974E6CD58E37293C494D2284592AD19DBB68EE45A0DB78D3560A84C4` |
| `tests/unit/capabilities/research_v2/test_content_acquisition.py` | `74F17512CDFAF20E378539CE4C306440D28636B4B61F4B5109482852DC036D40` |

## 后续组合约束与未验证项

- Task 7 的应用组合根创建一次 `LocalResearchNetworkLimits()`，对所有 Run 的工具工厂传同一 `network_limits`。当前接口已经强制必传；省略参数或传 None 都不能创建 Runtime。
- 每 Run 全程传播最初创建的 `BudgetExecutionBinding`；Acquirer 和 AcquisitionExecutor 共用该 ToolRuntime，并传该 Run 的权限、取消和 deadline。Task 3 的异步取消端口需由 Task 7 适配成 Runtime 的 CancellationPort。
- 五个现有来源配置仍禁用、原文许可仍未开放。测试中明确授权的 descriptor 是离线边界样本，不构成真实准入证据。
- 源码/离线测试不表示 Task 5～9 完成，不表示真实两轮研究成功或 production 就绪。未访问公网、模型或数据库，未重启服务，未读取 `.env`，没有 Git/Java/UI 操作。

## 独立复核 I1/I2/M1/M2 修复记录

四项均复现后修复，以下替代前文首次实现的对应行为和验证结论；待独立重新复核。

### I1：精确正文端点与查询参数授权

原有正文权限只有 host，复现时同 host 的未登记路径和任意查询均打开连接；同 host 未登记重定向也打开第二个连接。
定向 RED：`8 failed, 1 passed, 41 deselected in 2.56s`。

必要白名单扩展仅一个既有契约文件：`src/efficiency_platform_agent/contracts/research_sources_v2.py`，新增默认空的 `content_endpoints: tuple[str, ...]`。此字段是静态完整 URL 目录，不支持通配符、路径前缀或动态查询参数；查询键、值、顺序、重复键和编码均逐字匹配，不登记的无查询变体同样拒绝。
Tool factory 校验登记 URL 的形状和 host；Acquirer 在调用 Runtime 前检查目录；Fetch/每跳重定向重复检查同一目录。HN item API 也不得靠 host 自动获得平台文本获取权。

原契约逐字快照：`task4-review-before/research_sources_v2.py.snapshot`，SHA-256：`E49A53E2B22438E96619E516E7D970E34B38BC506ABD7DA8498A68794096CD2E`。
本报告修订前也保存在该目录 `Task4-文件级差异包.md.snapshot`。当前 TOML 未修改，五个来源的新字段默认空，不新增真实来源权限。

定向 GREEN：`9 passed, 41 deselected in 1.89s`。测试实际使用不同路径、不同查询值、额外查询键和缺失查询；入口负例 DNS/connector 均零调用；未登记重定向只发生第一跳。

### I2：摘要候选按独立正文授权重新获取

原有无条件 summary 拒绝会阻止获准的原文重取。定向 RED：`1 failed, 5 passed, 9 deselected in 2.37s`。
移除该无条件拒绝，继续要求正文用途许可、内容保存策略及精确 URL。inline 摘要从未传给正文解析器，成功测试观测到 `research.fetch.v2` 且实际连接一次，输出为重新获取的文章内容。
定向 GREEN：`6 passed, 9 deselected in 1.88s`，含无正文权限及伪 full 候选的零请求负例。

后续 Task 5 应根据本次成功重获正文的事实设置归一化内容范围，不能把原候选 inline summary 直接改标为 full；本任务未修改既有 normalization 或伪造发现来源语义。

### M1：平台非法 JSON 的稳定、安全错误

截断 JSON、非法 JSON、非法 UTF-8 三组 RED：`3 failed, 11 deselected in 2.38s`。
解析异常在处理块内消化，处理块外抛 `ValueError("SOURCE_SCHEMA_INVALID")`；不保留 JSONDecodeError/UnicodeDecodeError 的 cause/context/doc。定向 GREEN：`3 passed, 11 deselected in 1.79s`。

### M2：共享限流依赖失败关闭

省略参数及显式 None 两组 RED：`2 failed, 24 deselected in 2.36s`。
工厂签名把 `network_limits` 改成必传，并进行类型检查；工厂不再自行创建限流实例。测试中的单 Run 夹具显式创建实例，多 Run 测试共享同一实例。
遗漏依赖负例及双 Run 限流/取消隔离 GREEN：`4 passed, 22 deselected in 3.86s`。

### 复核修复后的完整验证

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py tests/unit/capabilities/research_v2/test_acquisition.py tests/unit/configuration/test_research_local_sources.py tests/contract/providers/research_v2 tests/architecture -q --tb=short
```

结果：`212 passed, 124 subtests passed in 20.95s`，退出码 0。包括 Task 4 原聚焦集合和全部架构；因增加契约字段，额外运行 Task 2 来源配置回归。
最后定向复验两个 Task 4 文件：`50 passed in 6.11s`。

```powershell
.venv\Scripts\python.exe -m mypy --follow-imports=silent src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py src/efficiency_platform_agent/contracts/research_sources_v2.py
.venv\Scripts\python.exe -m ruff check src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py src/efficiency_platform_agent/contracts/research_sources_v2.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
.venv\Scripts\python.exe -m compileall -q src/efficiency_platform_agent/harness/research_local_tools.py src/efficiency_platform_agent/capabilities/research/v2/content_acquisition.py src/efficiency_platform_agent/contracts/research_sources_v2.py tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py
```

结果依次为：mypy `Success: no issues found in 3 source files`；Ruff `All checks passed!`；格式检查 `4 files already formatted`；源码编译退出码 0。既有契约只增加字段与中文注释，不进行全文件格式化。

修订后的文档治理命令 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short`：`20 passed, 122 subtests passed in 5.12s`，退出码 0。

修复后 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `harness/research_local_tools.py` | `D84FD47EAFA2A77BF5186989562DEEEC6E5B61105A5F635A51B5BA5749EADEF4` |
| `capabilities/research/v2/content_acquisition.py` | `5477BFC17F348C0EB2940D4E0D6DCD46F53189586BF420977FDB0252A38D9A0B` |
| `contracts/research_sources_v2.py` | `D4DFA3A4B471A5CC7599EC65976BB1A8EB91968CA81CC28124E103642C6DA107` |
| `tests/unit/harness/test_research_local_tools.py` | `5D20276CC0DB69C3399A6B4E2EE6079A9079B15898FBA6B44EF60F3AC4106100` |
| `tests/unit/capabilities/research_v2/test_content_acquisition.py` | `8DE1C4AE4A49BB91072EBB9D2E90E7EE62AF6529A8A7938596D9BB97127074B0` |

前三条源码路径相对 `src/efficiency_platform_agent/`。没有遗漏本次四项复核问题；重审和 Task 5～9 未由该验证替代。未访问真实网络、模型、数据库或服务，未读取 `.env`，无 Git、UI、Java 或部署操作。

## 第二次复核：重定向策略拒绝必须不可重试

状态：实现与验证完成，待重新复核；更新时间：2026-09-17。

复现：第一跳 URL 已登记，302 指向同 host 未登记 `/private?download=all` 时，虽然第二跳未连接，`ResearchToolScopeError` 仍被 transport 的通用异常分支包为 `FETCH_TRANSPORT_FAILED`，导致 Tool 对外错误为可重试的 `SOURCE_TEMPORARY_FAILURE`。
先增强工具负例并新增正式 Acquirer 负例，RED 为 `2 failed, 49 deselected in 2.41s`，两个错误实际值均为 `SOURCE_TEMPORARY_FAILURE`。

最小修复仅在本任务 `harness/research_local_tools.py` 的 `_EndpointPolicy` 两个策略拒绝处使用既有 `ResearchFetchError("CONTENT_REJECTED", "SOURCE_NOT_RUNTIME_ALLOWED")`。transport 已能保留这种已分类错误，Tool 根据 reason 返回 `SOURCE_NOT_RUNTIME_ALLOWED` 且 `retryable=False`，Acquirer 则抛同码 ValueError。不修改公共 transport/工具代码，也不扩大异常捕获范围。

定向 GREEN：`3 passed, 49 deselected in 1.94s`。测试明确验证第一跳一个 socket、一次 DNS，父预算仅 Tool + HTTP 共 2 次；没有重复第一跳或新增来源配额。真实 connector OSError 仍返回 `SOURCE_TEMPORARY_FAILURE` 且可重试。

完整复验：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/harness/test_research_local_tools.py tests/unit/capabilities/research_v2/test_content_acquisition.py tests/unit/capabilities/research_v2/test_acquisition.py tests/unit/configuration/test_research_local_sources.py tests/contract/providers/research_v2 tests/unit/tools/test_tool_runtime.py tests/architecture -q --tb=short
```

结果：`237 passed, 124 subtests passed in 20.50s`，退出码 0。mypy 原三源码再次通过；Ruff 五文件通过，格式检查四文件通过，compileall 五文件退出码 0，命令范围与前节一致。

补充 `.venv\Scripts\python.exe -m pytest tests/unit/tools/test_research_tools.py tests/unit/tools/test_research_budget_adapter.py -q --tb=short`：`13 passed in 1.47s`。
更新文档后治理命令 `.venv\Scripts\python.exe -m pytest tests/governance/test_documentation_contract.py -q --tb=short`：`20 passed, 122 subtests passed in 3.98s`。均退出码 0。

本轮三项改动后 SHA-256（其余源码与前节相同）：

| 文件 | SHA-256 |
|---|---|
| `src/efficiency_platform_agent/harness/research_local_tools.py` | `BF7EE6A0C758B6D58D29B63C597C8F9DFB5A55D7DD37B3451BB53826CE87FFF9` |
| `tests/unit/harness/test_research_local_tools.py` | `A33378A05ECA69DE0EA629F1F2B3E645056602CC6B1A2492F5B08E7998A996E4` |
| `tests/unit/capabilities/research_v2/test_content_acquisition.py` | `E893B8CC906647CF60C78F2512D686C0EC85530A5E4EA6D4823BE31CD816F71A` |

继续保持纯 Agent、非 Git 和零真实网络/服务/模型/数据库边界，没有读取 `.env` 或修改 UI/Java/部署。
