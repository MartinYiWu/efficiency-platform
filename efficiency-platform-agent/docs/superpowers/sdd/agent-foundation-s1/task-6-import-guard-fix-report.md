# Task 6 Core 导入守卫修复报告

## 范围

仅修改 `tests/architecture/test_core_contracts.py` 的核心层静态依赖守卫；未修改生产代码、其他测试或既有文档。此报告为任务要求的验证证据。

## RED 证据

在变更前，以守卫原有的 AST 判定逻辑解析以下样例：

- `from .. import agents`
- `from .. import providers`
- `importlib.import_module("efficiency_platform_agent.agents")`
- `__import__("efficiency_platform_agent.providers")`
- `from importlib import import_module` 后调用 `import_module(...)`

静态检查退出码为 `1`，输出如下：

```text
CURRENT_GUARD_MISSES={'relative_agents': [], 'relative_providers': [], 'dynamic_agents': [], 'builtin_providers': [], 'direct_import_module_providers': []}
```

五个样例均未被记录为依赖，证明原守卫可被相对导入和动态加载绕过。

## GREEN 证据

守卫检测逻辑被收敛到同职责辅助方法，并新增回归用例。其覆盖相对 `agents`、相对 `providers`、`importlib.import_module`，以及同一动态导入入口的 `__import__` 和直接 `import_module` 调用形式。

执行：

```powershell
& .venv\Scripts\python.exe -m unittest tests.architecture.test_core_contracts -v
```

结果：退出码 `0`，`Ran 15 tests ... OK`；新增 `test_core_agent_dependency_guard_rejects_relative_and_dynamic_import_bypasses` 通过。

同时执行：

```powershell
& .venv\Scripts\python.exe -m unittest discover -s tests\architecture -v
```

结果：退出码 `0`，`Ran 28 tests ... OK`。

## 变更边界与未验证项

- 未修改 `src/` 下的生产代码，未改变现有 `core/agent.py` 的依赖状态。
- 未执行完整项目回归、Ruff 或 mypy；本任务的架构契约目标套件已执行。
- 工作区为非 Git 项目；未执行任何 Git 操作，审查以文件级测试证据为准。
