# S2 任务 6 实施报告：受治理 Tool Runtime 与合成 Tool

## 状态

已完成（离线 Tool Runtime 单元与契约 GREEN）；真实外部 Tool、MCP、网络和写操作未验证。

## 范围与文件

- `src/efficiency_platform_agent/tools/runtime/contracts.py`：冻结 `ToolSpec` 与 `ToolInvocationRecord` 字段及边界校验。
- `src/efficiency_platform_agent/tools/runtime/registry.py`：显式注册、descriptor 对齐校验、重复名称失败关闭。
- `src/efficiency_platform_agent/tools/runtime/service.py`：按注册→白名单→权限→副作用→Schema→预算→有界调用→结果/大小/审计顺序治理；支持 absolute timeout、可唤醒取消、最多两次无副作用重试，并在重试间维护单调的本地 Tool/Usage 预算快照。
- `src/efficiency_platform_agent/tools/internal/synthetic_lookup.py`：无外部 I/O 的固定合成查询结果。

## 新鲜验证证据

| 命令 | 实际结果 |
|---|---|
| `.venv\\Scripts\\python.exe -m pytest tests/unit/tools/test_tool_runtime.py tests/contract/runtime/test_tool_contract.py -q` | 12 passed，0 failures，0 errors，0 skipped |
| `.venv\\Scripts\\python.exe -m unittest tests.architecture.test_dependency_rules -v` | 10 tests，全部 OK |
| `.venv\\Scripts\\ruff.exe check src/efficiency_platform_agent/tools/runtime src/efficiency_platform_agent/tools/internal` | All checks passed |
| `.venv\\Scripts\\python.exe -m compileall -q src tests` | 通过 |

测试覆盖合法只读调用、注册/白名单/权限/副作用/参数/预算拒绝零调用、超时、失败重试、非重试失败、输出大小上限、结构化结果和合成 Tool 端口契约。重试失败会先扣除本地尝试预算及可信 output Token/费用，再决定是否继续。

## 边界声明

本任务未启动数据库、Redis、Provider、HTTP、MCP、外部 Tool、生产服务或部署；未执行 Java、Git、网络或外部写操作。当前证据仅证明 Python 3.13 本地进程内离线契约，不等于真实外部集成、跨进程恢复或生产可用。
