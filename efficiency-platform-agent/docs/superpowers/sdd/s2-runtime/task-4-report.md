# S2 任务 4：版本化 Prompt Runtime 实施报告

## 交付范围

- `prompts/contracts.py`：版本化 Prompt 契约。
- `prompts/registry.py`：显式唯一注册表。
- `prompts/runtime.py`：固定资源目录的安全渲染器。
- `prompts/resources/`：Direct、Workflow 草稿、Workflow 审校三份合成模板。

## 验证

```powershell
uv run pytest tests/unit/prompts/test_prompt_runtime.py -q
uv run ruff check src/efficiency_platform_agent/prompts tests/unit/prompts
uv run python -m compileall -q src/efficiency_platform_agent/prompts
```

结果：8 项测试通过；Ruff 和编译均退出码 0。

## 约束与未验证边界

渲染器使用 `ImmutableSandboxedEnvironment` 和 `StrictUndefined`，校验固定资源根目录、变量精确匹配、路径越界、未定义变量和最大长度；用户输入被置于不可信分区且不二次解析。本任务没有调用真实 Provider，未验证模型质量、真实运行链或业务 Prompt。
