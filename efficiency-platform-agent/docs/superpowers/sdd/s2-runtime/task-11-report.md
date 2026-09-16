# S2 任务 11：FastAPI Run API 与 SSE 最小入口

## 状态

- **已完成**：注入式 `create_app(service)`、六个 HTTP 入口、租户头校验、稳定错误映射、有限 SSE 回放与健康检查。
- **已完成**：API RED/GREEN 单元测试（`tests/unit/api/test_routes.py`），覆盖 201/200/202、422、403、404、409、敏感正文脱敏及 `Last-Event-ID` 续读。
- **未实现/未验证**：真实网络部署、Uvicorn 进程、Redis Streams 长连接/TTL、数据库持久化、跨进程恢复、生产容量和真实 Provider/Tool。

## 路由矩阵

| 方法 | 路径 | 行为 | 主要状态码 |
| --- | --- | --- | --- |
| POST | `/v1/runs` | 校验租户并调用注入服务创建/执行 | 201、403、422、409/500 |
| POST | `/v1/runs/{run_id}/resume` | 校验租户并恢复原 Run | 200、403、409、404 |
| POST | `/v1/runs/{run_id}/cancel` | 等待态取消；运行态协作取消 | 200、202、403、409、404 |
| GET | `/v1/runs/{run_id}` | 按租户查询安全视图 | 200、404 |
| GET | `/v1/runs/{run_id}/events` | 有限回放事件并输出 SSE | 200、400、404 |
| GET | `/health/live` | 仅报告 Fake/InMemory 模式 | 200 |

三个 POST 要求 `X-Tenant-ID` 与 body `tenant_id` 一致；不一致统一返回 `TENANT_MISMATCH`/403。入站 Pydantic 契约保持 `extra="forbid"`，新增字段返回 422。

## SSE 脱敏样例

```text
id: 2
event: run_succeeded
data: {"contract_version":"run.event/1","event_id":"event-2","event_type":"run_succeeded","run_id":"run-1","sequence":2,"occurred_at_epoch_ms":2,"status":"succeeded","payload":{}}
```

`Last-Event-ID` 仅接受正整数；缺失表示从 0 开始，非法游标返回 `INVALID_EVENT_CURSOR`/400。服务先按租户读取 `list_events(run_id, tenant_id, after_sequence)`，再将游标后的现有事件编码为 `id=sequence`、`event=event_type`、JSON `data`，回放结束即关闭连接。

## 证据

```text
uv run pytest tests/unit/api/test_routes.py -q
8 passed (1 Starlette deprecation warning)

uv run ruff check src/efficiency_platform_agent/api tests/unit/api/test_routes.py
All checks passed!

uv run mypy src/efficiency_platform_agent/api
Success: no issues found in 4 source files

uv run python -m compileall -q src/efficiency_platform_agent/api tests/unit/api/test_routes.py
exit 0

OpenAPI assertion: s2-openapi-ok
```

RED 阶段首次运行因环境未同步 pytest 而失败（`pytest` 不存在）；同步锁定开发依赖后按同一命令完成 GREEN。该证据仅证明 Fake/InMemory 离线 API/SSE 合约，不代表生产可用性。
