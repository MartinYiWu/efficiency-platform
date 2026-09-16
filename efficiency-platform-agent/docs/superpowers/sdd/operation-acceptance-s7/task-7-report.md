# S7 Task 7 实施报告：COS Artifact 隔离生命周期

新增注入式 `CosArtifactProvider`，通过 `asyncio.to_thread` 与并发信号量调用同步 COS SDK；对象 Key 固定为 `s7/{run_stamp}/{tenant_hash}/{artifact_id}`，限制最多 3 个对象、单对象 1 MiB，支持 Put/HEAD/Get/签名/Delete，并拒绝覆盖已有对象。仅保留内存索引与哈希，不记录签名 URL。

离线 Stub 测试覆盖生命周期、前缀隔离、租户哈希、大小/数量上限、覆盖保护、不安全 Key、对象内容完整性和缺失 SDK 方法失败关闭。`uv run python -m unittest tests.contract.providers.test_cos_provider_contract -q`：5 项通过；Ruff 与格式检查通过。未构造真实 COS 客户端、未读取 Secret、未执行网络。
