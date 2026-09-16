# S2 任务 5：唯一 Context Builder 实施报告

## 交付范围

- `src/efficiency_platform_agent/context/contracts.py`：不可变 `TrustLevel`、`ContextSource` 与 `BuiltContext` 契约。
- `src/efficiency_platform_agent/context/builder.py`：仅装配用户输入的最小 Context Builder。
- `tests/unit/context/test_context_builder.py`：身份、信任、顺序、Token、预算和工具白名单边界测试。

## 行为边界

- 只建立 `source_id="user_input"` 的单一来源，并标记 `USER_UNTRUSTED`；不读取 Memory、知识库、文件或环境。
- Token 估算固定为 `(len(input_text) + 3) // 4`；刚好达到输入预算允许，超出返回 `CONTEXT_BUDGET_EXCEEDED`。
- 请求与 `RunContext` 的 `tenant_id` 或 `user_id` 不一致时返回 `CONTEXT_IDENTITY_MISMATCH`。
- 工具白名单以不可变 `frozenset` 原样传递；用户文本不能增加工具或模型候选。错误消息不回显用户正文。

## 验证证据

```powershell
uv run pytest tests/unit/context/test_context_builder.py -q
```

历史实现文件临时移出后运行：收集阶段因 `ModuleNotFoundError: efficiency_platform_agent.context.builder` 失败，退出码 `2`；文件已立即恢复。

```powershell
uv run pytest tests/unit/context/test_context_builder.py tests/unit/prompts/test_prompt_runtime.py -q
```

结果：`14 passed`，退出码 `0`。

```powershell
uv run ruff check src/efficiency_platform_agent/context tests/unit/context tests/unit/prompts
uv run python -m compileall -q src tests
```

结果：Ruff `All checks passed`，编译退出码 `0`。

## 未验证边界

本任务未接入 Memory、RAG、文件上下文、真实 Provider、网络、数据库、Redis 或生产运行链；仅验证标准库/测试态 Context 与 Prompt 联合回归。
