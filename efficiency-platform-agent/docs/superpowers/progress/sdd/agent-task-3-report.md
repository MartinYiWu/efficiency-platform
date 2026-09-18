# Agent Task 3 实施报告

| 属性 | 内容 |
|---|---|
| 状态 | DONE；Task 3 目标、静态门禁与全量回归通过 |
| 负责人 | Agent Task 3 实施代理 |
| 适用范围 | 纯 Agent 侧 Prompt 注册与模型 Specialist 类型化交付 |
| 更新时间 | 2026-09-17 |
| 关联需求 | [Task 3 任务说明](agent-task-3-brief.md) |
| 版本治理 | 永久 non-Git；无提交 |

## 实施结果与接口裁决

- 显式提取 `build_operation_prompt_registry()`，同时注册 `operation.deliverable.generation/1` 与 `operation.deliverable.generation/2`；V2 模板覆盖中央 Supervisor、来源、平台差异、五类内容、复制文本与运行时 warning 边界。
- Specialist 新增固定 `deliverable_contract_version`；依据协调方阶段兼容裁决，构造器与组合根默认保持 `deliverable/1`，调用方显式传入 `deliverable/2` 才进入 V2。Task 4 完成聚合后再切换新 Run 默认。未知版本直接失败关闭，禁止模型自行切版本。
- 经协调方补充并更新 Task 3 Step 5 后，采用私有 Model Draft Schema。它继承正式五类业务字段，只覆盖 `citations=[]`、`copy_text=""`、`warnings=[]`；正式 Task 1 契约保持非空复制文本约束，未修改。
- Schema 名称依次为 `operation_ranked_digest`、`operation_platform_content`、`operation_action_plan`、`operation_diagnosis`、`operation_retrospective`；V1 保留 `operation_deliverable`。
- 来源 ID 优先取 EvidenceRecord ID，否则对规范 HTTPS URL 计算 SHA-256 前 20 位并加 `citation-` 前缀；小写 scheme/host、移除 fragment，完整保留 path/query，包括非空路径末尾斜杠。匹配 EvidenceRecord 后 title/source/id/date 整组取自该记录；没有记录时使用同一输入 citation 的元数据和 URL 派生 ID。来源类型、层级、核验状态固定为 `public_page/secondary/unverified`，发布日期仅取已有 epoch 的 UTC ISO，小写 hostname 作为独立来源组。
- 排名 `source_refs` 在结构修复前检查引用闭包；运行时反向生成 Citation 的 `supports_item_ids`。模型不能在条目中宣称高于现有来源的核验状态。
- 正式 V2 通过 Task 2 确定性渲染与展示验证；复制文本、来源、结构化 warning 全部由运行时生成。仅为既有质量报告生成 V1 投影，结果 payload 保留 V2，既有 SpecialistExecutionResult/OperationDeliverable 外壳不变。
- 每次调用保持 ModelRuntime/PromptRuntime 边界；没有 Provider SDK、联网、Java、UI、数据库、权限或调度拓扑改动。

## 修复与权限边界

- 只有结构 ValidationError 可触发一次修复 Prompt；再次结构失败立即结束。依据协调方补充裁决，唯一修复响应若明确为 `PROVIDER_RESPONSE_TRUNCATED`，可在剩余预算内重传相同消息一次；不生成第二次修复 Prompt，不允许第四次请求。
- 剩余迭代、输入/输出 Token、费用与超时均从实际执行消耗扣减；耗尽后不再请求。修复与传输重试的 max_tokens 和 timeout 随剩余预算收紧。既有 AgentSpec 的费用额度为零时，保留免费模型准入语义并交由 ModelRuntime 判断真实费用，不把零费用上限误当成禁止所有调用。
- 版本、平台、交付物 ID、交付类型、引用和权限字段错误先于结构校验失败关闭。混合“伪造引用 + 空标题”不会借结构修复获得重试。
- 校验使用 `strict=True`，排名字符串不自动转换为整数。Supervisor 目标专家不一致时，在模型调用前失败。

## RED 证据

首次新增测试后、生产实现前：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/prompts/test_prompt_runtime.py -q
```

退出码 1：`19 failed, 8 passed in 3.12s`。预期失败是缺少 `build_operation_prompt_registry`，没有把依赖错误或拼写错误计作功能证明。

补充严格类型、条目核验权限和 V1 混合引用错误测试后：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py -q
```

退出码 1：`3 failed, 22 passed in 2.23s`。失败分别为模型核验升级未拒绝、字符串排名被自动转换、V1 引用伪造混合结构错误触发第二次调用。修复后再执行 GREEN。

## GREEN 与质量门禁

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/agents/operation/specialists/test_model_backed_citations.py tests/unit/prompts/test_prompt_runtime.py -q
```

退出码 0：首次 GREEN 为 `28 passed in 1.79s`；补充边界后为 `35 passed in 1.78s`。

```powershell
.venv\Scripts\python.exe -m pytest tests/architecture/test_dependency_rules.py tests/contracts/test_deliverable_v2_contracts.py tests/unit/agents/operation/test_delivery_kind.py tests/unit/capabilities/quality/test_deliverable_v2.py -q
.venv\Scripts\python.exe -m compileall -q src tests
.venv\Scripts\python.exe -m ruff check src/efficiency_platform_agent/agents/operation/specialists/model_backed.py src/efficiency_platform_agent/harness/operation_agent_factory.py tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/prompts/test_prompt_runtime.py
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/agents/operation/specialists/model_backed.py src/efficiency_platform_agent/harness/operation_agent_factory.py tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/prompts/test_prompt_runtime.py
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent/agents/operation/specialists/model_backed.py src/efficiency_platform_agent/harness/operation_agent_factory.py tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/prompts/test_prompt_runtime.py
```

结果：`49 passed, 47 subtests passed in 3.40s`；编译退出码 0；`All checks passed!`；`4 files already formatted`；`Success: no issues found in 4 source files`。

## 初次全量回归失败与阶段裁决闭环

```powershell
.venv\Scripts\python.exe -m pytest -q
```

退出码 1：`25 failed, 1605 passed, 9 skipped, 2 warnings, 280 subtests passed in 63.95s`。

失败分布：

- `tests/acceptance/test_research_backed_multi_platform.py`：3 项。
- `tests/acceptance/test_research_v2_closed_loop.py`：1 项。
- `tests/integration/test_operation_agent_runtime.py`：19 项。
- `tests/unit/harness/test_local_real_factory.py`：1 项。
- `tests/governance/test_documentation_contract.py`：1 项。

24 项运行链失败涉及组合根默认 V2 后，既有 fake model 输出仍为 `deliverable/1`、旧聚合仍消费 V1；代表错误为 `OPERATION_ALL_SPECIALISTS_FAILED`。协调方随后明确 Task 3 只提供 V2 显式选择、默认保留 V1，并保留唯一修复响应截断的一次相同请求传输重试。Task 4 再迁移聚合与切换默认。

文档门禁失败来自协调方同步的实施计划里 `citation-` 示例后的三个点被治理测试识别为未经允许的占位符，已通知协调方处理。本代理未修改该清单外计划文件。

按新裁决先补测试，执行 Specialist 单文件得到 RED：`2 failed, 25 passed in 4.14s`，失败为默认 V1 和截断传输重试尚不存在。实现后联合运营集成发现三项失败，定位为既有零费用预算被错误拦截；修复后执行目标三文件加 `tests/integration/test_operation_agent_runtime.py`，结果 `69 passed in 2.51s`。更新后的四文件 Ruff/format/mypy 和源码编译通过。

最终重跑 `.venv\Scripts\python.exe -m pytest -q`：退出码 0，`1632 passed, 9 skipped, 2 warnings, 280 subtests passed in 56.09s`。此前 25 项失败均已消失；没有为该回归修改 Task 4 或清单外测试实现。

两条 warning 为既有 Starlette alias 弃用和 Polars Excel future behavior。未进行真实 Provider、网络、数据库或生产环境验收；V2 仍是显式 Specialist 能力，不能声称 V2 聚合或端到端上线完成。

## 文件快照清单

| 文件 | SHA256 |
|---|---|
| `src/efficiency_platform_agent/prompts/resources/operation/deliverable_generation_v2.j2` | `B51691F3077ECCFA5D61FC31E3846CEC421109287709C86E10330EF153CAD26B` |
| `src/efficiency_platform_agent/harness/operation_agent_factory.py` | `880BB438ECBBC5796418A40D8755550CED5CF9C1EF06580F4402A6DE6FD3D1F5` |
| `src/efficiency_platform_agent/agents/operation/specialists/model_backed.py` | `886DA1BDA2DA3DEB58050BB15106EBBE08B49C81D8A718C1DAF6613B90D347A9` |
| `tests/unit/agents/operation/specialists/test_model_backed_v2.py` | `6A3625E6E441E222DC9B19E6662470181A6320CD96833D644BC53C25B51DB4C3` |
| `tests/unit/prompts/test_prompt_runtime.py` | `0FD5A6EC402117D74C21BB3F4EF7BF87350EFA9AC043AD36D959594464C79A5D` |

另新增本报告并只追加正式进度账本；未执行任何 Git 命令，未创建提交。

## 独立复核 Important 修复：来源 URL 与元数据关联

复核发现 `_source_url()` 无条件去掉路径末尾斜杠，把 `https://example.com/news/?id=1` 与 `https://example.com/news?id=1` 合并，造成证据字典覆盖和来源元数据混合。按 TDD 先新增有 EvidencePack/无 EvidencePack 两种 URL 对照及整组元数据来源测试，再实施三行最小修复。

RED 命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py -k 'path_trailing_slash or evidence_metadata_is_selected' -q
```

退出码 1：`3 failed, 27 deselected in 2.34s`。两个路径对照测试均实际只生成 1 条 citation；有证据场景的失败输出明确展示 `citation_id='evidence-b'` 搭配 `title='Article A'`。整组元数据测试则显示 title/source 来自另一份展示数据而 ID/date 来自 EvidenceRecord。

修复完整保留 URL path 的斜杠；有匹配证据时 title/source 与 id/date 一起来自 EvidenceRecord，没有证据时保留原 citation 的元数据。未改 Task 1/2 契约和验证器，未改变 V1 默认与请求次数策略。

GREEN 与门禁命令：

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py -q
.venv\Scripts\python.exe -m pytest tests/unit/agents/operation/specialists/test_model_backed_v2.py tests/unit/agents/operation/specialists/test_model_backed_citations.py tests/unit/prompts/test_prompt_runtime.py -q
.venv\Scripts\python.exe -m pytest tests/architecture/test_dependency_rules.py -q
.venv\Scripts\python.exe -m compileall -q src tests
.venv\Scripts\python.exe -m ruff check src/efficiency_platform_agent/agents/operation/specialists/model_backed.py tests/unit/agents/operation/specialists/test_model_backed_v2.py
.venv\Scripts\python.exe -m ruff format --check src/efficiency_platform_agent/agents/operation/specialists/model_backed.py tests/unit/agents/operation/specialists/test_model_backed_v2.py
.venv\Scripts\python.exe -m mypy src/efficiency_platform_agent/agents/operation/specialists/model_backed.py tests/unit/agents/operation/specialists/test_model_backed_v2.py
```

结果分别为 `30 passed in 2.02s`；`40 passed in 2.21s`；`12 passed, 47 subtests passed in 2.16s`；编译退出码 0；`All checks passed!`；`2 files already formatted`；`Success: no issues found in 2 source files`。

本次修复仅作用于 V2 来源转换，使用实际 Specialist 运行结果覆盖新旧 URL、证据关联和现有 V1 引用测试，未再次执行全量回归；前述 `1632 passed` 是本次复核修复前的历史全量证据。最终两个变更文件 SHA256 已更新到上方快照表。状态：DONE，无提交。
