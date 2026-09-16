# Task 4 执行报告：对话级联网研究路由

| 项目 | 记录 |
|---|---|
| 状态 | DONE |
| 范围 | 意图提示中的研究路由约束；会话级研究冲突规范化；既有 `industry_digest` 研究链复用；研究 Gate 关闭时的失败关闭与离线验证 |
| 非范围 | ModelRuntime、GeneralConversationAgent、输出治理、前端、外部 Provider 实现、独立搜索框架与真实网络调用 |
| 风险级别 | 中：研究请求不可落入无工具 DIRECT；通过受控既有场景、Gate 和证据门保持失败关闭 |

## RED 证据

在任何生产代码修改前，先新增意图提示、冲突路由和可见历史主题继承测试，并执行：

```powershell
uv run pytest tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py -q
```

结果：`3 failed, 96 passed`。

- 意图提示缺少稳定知识与显式搜索/最新/核实/来源的 `industry_digest` 约束。
- 两个 `general_chat + needs_research=true` 测试均没有研究提交，证明旧逻辑把矛盾状态直接送入 DIRECT。

为覆盖“最终回答说明最新默认窗口”，在该生产行为写入前先补充目标传播断言并运行：

```powershell
uv run pytest tests/api/test_conversation_routes.py::test_general_chat_research_conflict_routes_to_industry_digest -q
```

结果：`1 failed`，任务目标未包含 `最近7天（默认最新信息窗口）`，无法保证 Research Specialist 与最终交付上下文可见该约束。

## 交叉审查补充 RED 证据

先新增两类回归测试，未修改对应生产代码即执行：

```powershell
uv run pytest tests/api/test_conversation_routes.py -q
```

结果：`2 failed, 42 passed`。`帮我查一下最新的` 与 `请给我来源` 即使被解释器错分为 `general_chat + needs_research=false`，仍进入 DIRECT；测试同时证明主题错误地取自短追问而非可见 user 历史。

随后将相同测试扩展为 `帮我搜一下最新的` 与 `请帮忙核实一下` 两种自然语言变体；生产代码未变时结果为 `2 failed, 2 passed`，两者均错误地把解释器的“普通问答”当作主题。补齐短追问词表后，四种表达都从可见 user 历史继承主题。

独立复核继续补充带主题误分类用例：`请搜索机器人行业最新动态` 被解释器标为 `general_chat + needs_research=false` 且通用目标为“回答用户问题”。执行单测得到 `1 failed`，主题错误取“回答用户问题”。最小修复后，显式泛指追问优先可见历史、误分类的显式带主题请求优先当前消息，非显式和已标记研究请求仍保持受控意图字段优先。

```powershell
uv run pytest tests/unit/harness/test_local_real_factory.py::test_factory_research_gate_off_fails_without_model_fallback -q
```

结果：`1 failed`，Fake 模型调用索引为 `2`（意图解释后仍调用了普通运营专家），而测试要求为 `1`。这证明研究 Gate 关闭时存在无证据模型回退。实现首次完成后，再收紧透明错误码断言得到第二个有效 RED：终态为失败但错误码仍是 `OPERATION_ALL_SPECIALISTS_FAILED`，未明确研究能力不可用。

## 最小实现

- 在 `_FIELD_SPECIFICATION` 中明确：稳定知识使用 `general_chat + needs_research=false`；明确搜索、最新、核实、来源使用 `industry_digest` 且同时设定研究/多 Agent 标记。
- 会话服务在进入 DIRECT 判定前，将带研究标记的 `general_chat`（及不完整的 `industry_digest`）规范化到既有 `industry_digest`，不新增场景、运行时或 Provider。
- 主题优先采用受控意图字段和明确目标；“那查一下最新的”“给我来源”等无主题追问从可见用户历史继承主题；确无主题时保留 `topic` 缺失并进入既有澄清路径。
- “最新”无时间范围时使用可审计的 `最近7天（默认最新信息窗口）`，同时写入研究任务目标以要求最终回答说明默认窗口；其他研究请求保留“未限定时间范围（公开资料核验）”。
- ConversationService 额外检测“搜索、查一下、查询、核实、最新、来源、联网”等显式研究词；该确定性兜底不依赖解释器的 `needs_research`。显式泛指追问优先继承可见 user 历史，误分类的显式带主题请求优先当前消息；非显式请求和已标记研究请求仍保留受控意图字段优先。
- `operation.research.insight` 始终使用既有 `ModelBackedResearchSpecialist`。当 Gate 关闭而未注入研究端口时，组合根注入仅返回 `RESEARCH_UNAVAILABLE` 的内存失败替身，绝不回退普通模型专家。
- 调度器只白名单透传 `RESEARCH_UNAVAILABLE`；场景聚合保留该稳定错误码。其余 Specialist 失败仍使用既有泛化码，避免将任意 Provider 或模型文本写入事件。

## GREEN 与验证证据

```powershell
uv run pytest tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py -q
```

结果：`99 passed in 3.78s`。

```powershell
uv run ruff check src/efficiency_platform_agent/orchestration/intent_interpreter.py src/efficiency_platform_agent/conversation/service.py tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py
```

结果：`All checks passed!`。

```powershell
uv run python -m compileall -q src/efficiency_platform_agent/orchestration/intent_interpreter.py src/efficiency_platform_agent/conversation/service.py
uv run python -m unittest tests.architecture.test_dependency_rules -v
uv run pytest tests/unit/agents/operation/specialists/test_research_quality.py -q
```

结果：源码编译成功；架构守卫 `12` 项全部通过；既有 Research Specialist 质量测试 `4 passed`，保留 Provider 失败、来源为空与 Evidence Gate 失败时关闭的行为以及成功引用关联。

交叉审查补充后的最终验证：

```powershell
uv run pytest tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py tests/integration/test_operation_agent_runtime.py -q
uv run ruff check src/efficiency_platform_agent/conversation/service.py src/efficiency_platform_agent/harness/operation_agent_factory.py src/efficiency_platform_agent/strategies/multi_agent/scheduler.py src/efficiency_platform_agent/orchestration/supervisor.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py tests/integration/test_operation_agent_runtime.py
uv run python -m compileall -q src/efficiency_platform_agent/conversation/service.py src/efficiency_platform_agent/harness/operation_agent_factory.py src/efficiency_platform_agent/strategies/multi_agent/scheduler.py src/efficiency_platform_agent/orchestration/supervisor.py
uv run python -m unittest tests.architecture.test_dependency_rules -v
```

结果：`128 passed in 3.39s`；Ruff `All checks passed!`；源码编译成功；架构守卫 `12` 项全部通过。

## 修改文件

- `src/efficiency_platform_agent/orchestration/intent_interpreter.py`
- `src/efficiency_platform_agent/conversation/service.py`
- `src/efficiency_platform_agent/harness/operation_agent_factory.py`
- `src/efficiency_platform_agent/strategies/multi_agent/scheduler.py`
- `src/efficiency_platform_agent/orchestration/supervisor.py`
- `tests/orchestration/test_intent_interpreter.py`
- `tests/api/test_conversation_routes.py`
- `tests/unit/harness/test_local_real_factory.py`
- `tests/integration/test_operation_agent_runtime.py`
- `docs/superpowers/sdd/realtime-conversation/task-4-report.md`

## 自查结论

- 明确研究请求不会直接进入 DIRECT；已覆盖冲突态到 `industry_digest` 的策略与提交断言。
- 可见上下文的主题继承只读取受限 user turn；无主题短追问不被误当成主题。
- Gate 关闭或研究端口返回不可用时，研究任务以 `RESEARCH_UNAVAILABLE` 透明失败、没有成品且不调用普通模型专家；成功路径仍只接受研究端口提供的引用。
- 沿用既有 `industry_digest`、Research Specialist、Evidence Gate、质量门和引用链；未引入付费数据源或新的搜索框架。
- 所有验证使用合成配置、Fake Provider 或离线测试；未读取 `.env`、未运行 Git、未启动常驻服务。
