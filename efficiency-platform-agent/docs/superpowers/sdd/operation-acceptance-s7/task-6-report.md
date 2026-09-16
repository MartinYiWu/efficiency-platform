# S7 Task 6 实施报告

## 完成内容

- 新增 `RedisRunEventStore`，消费 S2 `RunEventRecord`/`RunEventStore` 形状，使用注入客户端投递短期 Stream。
- Stream Key 固定为 `s7:{run_stamp}:events`，默认 TTL 900 秒、最多 20 条事件、载荷字节上限和单调 sequence 校验。
- 支持事件 ID 幂等、按 sequence 与 Last-Event-ID 续读；有 `xrange` 能力时从 Redis Stream 回读，支持新进程实例恢复短期事件窗口，并在关闭时仅关闭注入客户端。
- 新增 `SingleWorkerTaskBroker` 离线 Taskiq 边界，任务 Key 固定为 `s7:{run_stamp}:tasks`，支持 TTL 900 秒、最多 20 条消息、幂等键、协作式取消和稳定失败归一化；有 `xrange`/Set 能力时可从 Redis 恢复幂等索引与取消标记。
- 新增 `AcceptanceProbe`，只接受 `run_stamp/task_id/sequence` 合成字段，拒绝正文、Secret、文件和任意函数名；所有适配器均不创建真实客户端、不启动 Worker。

## 验证证据

```text
uv run pytest tests/contract/providers/test_redis_provider_contract.py tests/integration/s7/test_redis_taskiq.py -q
9 passed
uv run ruff check src/efficiency_platform_agent/providers/cache/redis.py src/efficiency_platform_agent/tasks/broker.py src/efficiency_platform_agent/tasks/acceptance_probe.py tests/contract/providers/test_redis_provider_contract.py tests/integration/s7/test_redis_taskiq.py
All checks passed
uv run mypy src/efficiency_platform_agent/providers/cache/redis.py src/efficiency_platform_agent/tasks/broker.py src/efficiency_platform_agent/tasks/acceptance_probe.py
Success: no issues found in 3 source files
```

RED 证据：首次运行契约测试因 `providers.cache.redis` 不存在而出现 `ModuleNotFoundError`；随后实现最小适配器并通过上述离线测试。

## 未执行范围

未执行 Redis PING、Taskiq Worker、网络探测、写入/计费验收或清理动作；未调用 `FLUSHDB`、`FLUSHALL`，也未修改 S2～S6 生产契约。真实 G4 仍需独立授权后执行。
