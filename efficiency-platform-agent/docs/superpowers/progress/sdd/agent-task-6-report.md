# Agent Task 6：安全、兼容和全量门禁实施报告

| 属性 | 内容 |
|---|---|
| 状态 | `DONE_WITH_CONCERNS`，R2 测试补强完成，待独立复核 |
| 负责人 | Agent Task 6 实施代理 |
| 日期 | 2026-09-17 |
| 范围 | V2 交付展示安全、冻结样例、回归与全量门禁 |
| Git | 项目永久 non-Git；本任务未执行 Git 命令 |

## 实施结果

- `DeliveryPresentationValidator` 在渲染 `copy_text` 后递归检查所有公开展示字段；结构化内部标识、计数、来源引用 ID 与下一轮 `intent_patch` 不读取、不改写。
- V2 引用只接受无任意空白字符、具有 hostname、无用户名/密码的 HTTPS URL；协议和 hostname 的大小写不会造成误杀。
- 用户可见字段拒绝 NFKC 标准化后出现的 `<script`、`javascript:`、`system prompt`、`hidden reasoning` 标记。标题、导语、来源标题、排序摘要、Markdown、确定性纯文案、集合摘要、warning 和后续动作标签均经同一边界检查。
- 新增独立安全测试，覆盖恶意 URL、内部/主动标记、跨交付物引用、Markdown、普通 `token` 业务文本、内部 `intent_patch` 保持不变及安全 HTTPS 大小写边界。
- 正式进度账本固定一份可由 `DeliverableSetV2.model_validate()` 解析的离线 JSON：9 个虚构热点、2 个 `example.test` 来源、一个 `rewrite_for_platform` 动作、provenance 与空 warnings；治理测试直接解析该账本片段防止后续漂移。

## 已批准的最小范围扩展

新增安全门正确拒绝共享研究 fixture 中会直达用户交付的 `<script>` 标题。经协调方批准，仅完成如下测试 fixture 同步，不改研究行为、URL 规则或安全边界：

- `tests/unit/capabilities/research_v2/_delivery_support.py`：共享虚构来源标题改为 `Acme 离线验证结果`。
- `tests/unit/capabilities/research_v2/test_delivery.py`：对应的单一字面断言同步为安全标题。

独立安全测试仍保留 `<script` 拒绝，不把恶意输入改成可接受行为。

## R2 独立复核修复：研究 Markdown 恶意来源标题回归

独立复核指出，共享 fixture 已换成安全标题后，原研究 Markdown 测试不再实际证明
恶意来源标题会被转义。仅在
`tests/unit/capabilities/research_v2/test_delivery.py` 增加一个独立构造的
`DeliveryPackV2`：其来源标题包含 `<script>alert('unsafe')</script>`，不复用
共享 fixture，也不改动生产渲染器。断言输出含 `&lt;script&gt;` 与
`&lt;/script&gt;`，并且不含原始 `<script>` 标签。

测试先行的首个精确文本断言得到 RED：渲染器除了 HTML 转义外还会按 Markdown
规则转义圆括号，故断言未覆盖其合法的更严格输出。随后把断言收敛为本任务要求的
安全语义（两个 HTML 标签均已转义、原始标签不可出现），GREEN：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\capabilities\research_v2\test_delivery.py -q
```

结果：`4 passed in 1.63s`。该修复只增加回归证明，不改变生产安全边界。

## TDD 证据

安全测试先创建并运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\security\test_deliverable_v2_safety.py -q
```

RED：`10 failed, 2 passed in 1.17s`。失败分别证明不安全 URL、主动内容和内部提示标记在既有实现中可透传。

实现最小检查后，曾因补丁将既有 action target 校验尾段错置而引发 `NameError`；立即按原语义恢复到 `_validate_next_actions`，不改变动作规则。最终安全、质量与账本治理聚焦验证：

```powershell
.venv\Scripts\python.exe -m pytest tests\security\test_deliverable_v2_safety.py tests\unit\capabilities\quality\test_deliverable_v2.py tests\governance\test_operation_chat_acceptance.py -q
```

GREEN：`60 passed in 0.94s`。

冻结样例账本测试先运行：

```powershell
.venv\Scripts\python.exe -m pytest tests\governance\test_operation_chat_acceptance.py -k frozen_v2_sample -q
```

RED：`1 failed, 25 deselected in 0.99s`，原因是账本尚无指定标记的样例。写入样例后 GREEN：`1 passed, 25 deselected in 0.58s`。

## 回归与质量门禁

| 命令 | 结果 |
|---|---|
| Task 1–5 关联套件（契约、Specialist、Prompt、V2 聚合、SSE、EventHub、安全、治理） | `226 passed in 4.41s` |
| 共享 fixture/Research V2/安全回归 | `35 passed in 4.09s` |
| `pytest tests/architecture/test_dependency_rules.py -q` | `12 passed, 47 subtests passed in 2.37s` |
| `python -m compileall -q src tests` | 退出码 0 |
| `python -m ruff check src tests` | `All checks passed!` |
| `python -m mypy src` | `Success: no issues found in 291 source files` |
| 本任务 5 个 Python 文件 `ruff format --check` | `5 files already formatted` |
| 全库 `ruff format --check src tests` | 退出码非 0；`98 files would be reformatted, 463 files already formatted`，均不在本任务白名单，未越界批量格式化 |
| `uv audit --frozen` | 发现 `accelerate 1.14.0` 的 2 条已知漏洞，均无可用修复版本：PYSEC-2026-3804、GHSA-4j2p-28q2-5m79 |

## 全量 pytest 与未掩盖基线失败

最终全量命令：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

结果：`1 failed, 1712 passed, 9 skipped, 2 warnings, 280 subtests passed in 56.08s`。

唯一失败可用最小命令稳定复现为 `1 failed, 8 passed in 0.85s`：

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\harness\test_live_acceptance.py -q
```

失败断言位于 `test_authorization_cannot_be_reused_with_a_new_request_id`：测试已正确捕获第二个 request 的 `LIVE_AUTHORIZATION_REUSED`，却仍要求 runner 执行 `ordinary_chat`。真实调用链为 `LiveAcceptanceService.execute` 在调用 runner 前调用 `InMemoryLiveAcceptanceBudgetBinder.bind`；该 binder 对相同 authorization 的不同 request fingerprint 立即抛出 `LIVE_AUTHORIZATION_REUSED`。本任务未改 Harness、LiveAcceptance 或该测试，质量模块也不导入该路径，因此不修改无关实现或断言来掩盖该基线冲突。

两个 warning 分别来自既有 Starlette `BlockingPortal` 弃用提示和 Polars Excel future behavior，均不在本任务修改路径。

## 文件快照

| 文件 | SHA256 |
|---|---|
| `src/efficiency_platform_agent/capabilities/quality/deliverable_v2.py` | `2471919EC9BCCD0A8BBCA7811EB3C5E28C254E27CFF5C0AC2DCBC67B98DEDFAB` |
| `tests/security/test_deliverable_v2_safety.py` | `937026B69EB9D2769B1C4B285AC15EA2936F49174368ED16B84C8B2CEF6AC864` |
| `tests/governance/test_operation_chat_acceptance.py` | `84391C4ED3793BA63BE70B32003ABCC35532E261EF152CFD9594B393F9BEDF67` |
| `tests/unit/capabilities/research_v2/_delivery_support.py` | `90EB428AF9A42DDB1795BCE6671F9CDEAAC2FC6B19817C16F2058898009648BA` |
| `tests/unit/capabilities/research_v2/test_delivery.py` | `5E1EA63C17971E4C7C717ACF65CAD49A5432C68F699CF3A11603DA33344AE397` |

## 未验证边界

- 未执行真实 Provider、网络来源、数据库、前端联调或生产 SSE 验收。
- 未处理全库 98 个历史格式问题、无修复版本的第三方漏洞或无关 LiveAcceptance 断言冲突。
- 本任务只提供自动化/静态证据，后续由独立复核确认规格与代码质量。

## R2 回归与复核前状态

关联的 Task 1–5 与 Task 6 安全、质量、治理、Research V2、Operation V2 SSE/
EventHub 套件共 `291 passed in 6.48s`；AST 依赖守卫为 `12 passed, 47 subtests
passed in 1.94s`；`compileall`、全库 `ruff check` 以及本测试文件
`ruff format --check` 均退出码 0。

最新全量 `.venv\Scripts\python.exe -m pytest -q`：`1 failed, 1713 passed, 9 skipped,
2 warnings, 280 subtests passed in 52.31s`。唯一失败仍为未触及的
`tests/unit/harness/test_live_acceptance.py::test_authorization_cannot_be_reused_with_a_new_request_id`：绑定器在第二个不同 request 的授权绑定阶段正确抛出
`LIVE_AUTHORIZATION_REUSED`，测试却期待后续 runner 已执行。R2 不导入或修改该
Harness 路径，未掩盖该既有冲突。Starlette 与 Polars 的两条 warning 仍为既有依赖
提示。

R2 文件 SHA256：`tests/unit/capabilities/research_v2/test_delivery.py` 为
`9A795AAA00AC139ECC3111FD1E0B07B1D87605830A0BE67FC6C4A7CF6A2FBAE9`。状态保持
`DONE_WITH_CONCERNS`，等待独立复核。
