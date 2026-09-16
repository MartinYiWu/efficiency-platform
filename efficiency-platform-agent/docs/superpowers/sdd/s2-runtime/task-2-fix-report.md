# S2 任务 2 修复报告

## 修复内容

- `RunEventRecord` 现在递归检查 `JsonObject`、字典、元组等 JSON 容器中的敏感键；`strategy_event` 的信封键也递归执行白名单校验。
- `RunRecord.__post_init__` 现在与 `transition()` 使用相同的终态和输出/失败不变量，拒绝直接构造非法权威快照。
- 原始 `task-2-core-red.txt` 保留为历史事实；新增测试先行修复用例，未伪造或覆盖历史 RED 输出。

## 验证

执行：

```powershell
uv run pytest tests/unit/core/test_budget_guard.py tests/unit/core/test_runtime_contracts.py tests/contract/runtime/test_event_contract.py -q
```

结果：33 passed，退出码 0。

未验证：S2 任务 3～12 的进程内存储、Prompt、Context、Tool、Provider、Graph、Harness、API 和真实外部集成。
