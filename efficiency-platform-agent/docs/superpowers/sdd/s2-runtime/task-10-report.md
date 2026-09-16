# S2 任务 10：Harness 组合根与运行服务

## 状态

已完成（离线 Harness 单元 GREEN，待阶段级复核）。

## 实际文件

- `src/efficiency_platform_agent/harness/errors.py`
- `src/efficiency_platform_agent/harness/service.py`
- `src/efficiency_platform_agent/harness/factory.py`
- `src/efficiency_platform_agent/contracts/requests.py`
- `src/efficiency_platform_agent/contracts/responses.py`
- `src/efficiency_platform_agent/contracts/events.py`
- `tests/unit/harness/test_harness_service.py`

## RED/GREEN

先建立 Harness 生命周期测试；实现前模块缺失导致导入失败。实现后：

```text
uv run pytest tests/unit/harness/test_harness_service.py -q
5 passed

uv run ruff check src/efficiency_platform_agent/contracts src/efficiency_platform_agent/harness
All checks passed

uv run mypy src/efficiency_platform_agent/contracts src/efficiency_platform_agent/harness
Success: no issues found
```

## 已实现边界

- 显式注入 Repository、EventStore、Router、GraphRuntime、BudgetGuard、Clock 和 ID 生成器；
- 创建流程包含租户级幂等、Run 生命周期事件、策略选择、payload 适配和 Graph 执行；
- 查询、恢复、取消和事件回放均经过 Harness；
- `build_s2_test_service()` 只装配 InMemory/Fake 组件，不读取环境配置或连接外部系统；
- 对外响应使用版本化 Pydantic 契约，错误消息不回显内部异常。
- Checkpoint 事件在 Run CAS 成功后才追加，避免对外暴露尚未完成的权威状态变更。
- 恢复值严格要求版本化完整字段并拒绝未知字段，绑定不匹配时以稳定错误码失败关闭。

## 未验证边界

- FastAPI/SSE 尚未实现；
- 六组完整 acceptance、运行中取消唤醒、预算各维度严格前后治理仍待任务 11/12 完善；
- 尚未调用真实 Provider、网络、数据库、Redis、COS 或 MCP；
- InMemory 存储未验证跨进程持久化、并发压力和生产环境。
