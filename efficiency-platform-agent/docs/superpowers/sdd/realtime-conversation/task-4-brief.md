# Task 4 任务简报：对话级联网研究路由

## 目标

让明确要求搜索、最新信息、核实或来源的会话进入现有受控研究链，而不是进入无工具 DIRECT；保持证据门、引用、Gate、预算和失败透明。

## 文件所有权

- 可修改：`src/efficiency_platform_agent/orchestration/intent_interpreter.py`
- 可修改：`src/efficiency_platform_agent/conversation/service.py`
- 可修改：`src/efficiency_platform_agent/agents/operation/scenarios/manifests.py`（仅新增轻量会话研究场景确有必要时）
- 可修改：`src/efficiency_platform_agent/orchestration/scenario_resolver.py`（仅契约确需时）
- 可修改对应 `tests/orchestration/test_intent_interpreter.py`、`tests/api/test_conversation_routes.py`、`tests/unit/harness/test_local_real_factory.py`。
- 不得修改 ModelRuntime、Harness、GeneralConversationAgent、输出治理或前端文件。

## 必须满足

- 先写失败测试并实际确认按预期失败，再写生产代码。
- 意图 Prompt 明确：稳定知识为 `general_chat + needs_research=false`；明确搜索、最新、核实、来源的请求必须进入研究场景或至少产生 `needs_research=true`。
- `general_chat + needs_research=true` 是矛盾状态，不得直接进入 DIRECT。
- 优先复用现有 `industry_digest` / Research Specialist；只有它无法表达自然会话研究时，才增加最小 `conversational_research` 场景，不新增运行时或 Provider。
- 上下文追问“那查一下最新的”“给我来源”要从可见会话继承主题；只有主题确实无法确定时才澄清。
- 时间范围未明确但用户要求“最新”时，使用明确且可审计的默认窗口并在最终回答中说明；不要为纯技术缺省询问用户。
- Gate 关闭、Provider 失败或来源为空时不得声称已联网成功，只描述本次未能完成在线核验。
- 研究成功必须保留经过既有证据门验证的引用。
- 不引入付费数据源或独立搜索框架。
- 所有新增注释和 Docstring 使用中文；不读取 `.env`，不运行 Git，不启动常驻服务。

## 验证

至少运行：

```powershell
uv run pytest tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py -q
uv run ruff check src/efficiency_platform_agent/orchestration/intent_interpreter.py src/efficiency_platform_agent/conversation/service.py tests/orchestration/test_intent_interpreter.py tests/api/test_conversation_routes.py tests/unit/harness/test_local_real_factory.py
```

把 RED 命令/失败原因、GREEN 命令/结果、修改文件、自查结论写入 `task-4-report.md`。
