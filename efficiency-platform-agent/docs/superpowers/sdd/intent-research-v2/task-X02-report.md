# X02 实施报告：组合根、会话协议、兼容与开关

## 状态

**离线通过。**

X02 已完成默认关闭的 ResearchPipelineSettings、任务级版本冻结适配器、真实组合根的显式 V2 依赖门禁、V1 受控终态/事件投影和禁用旧未知收费搜索规则。X01 PostgreSQL 集成仍阻塞，因此本结论不包含生产持久化。

## 交付文件

- `src/efficiency_platform_agent/configuration/research.py`
- `src/efficiency_platform_agent/configuration/__init__.py`
- `src/efficiency_platform_agent/conversation/intent_v2_adapter.py`
- `src/efficiency_platform_agent/harness/local_real_factory.py`
- `config/research_pipeline.toml`
- `tests/unit/harness/test_research_v2_factory.py`
- `tests/contracts/test_research_v2_compatibility.py`

## 已实现不变量

- 仓库配置固定 `intent-v1/research-v1`、replan false、空 allowlist、memory backend；默认不启用 V2、不声明生产就绪。
- 只有 Intent/Research 两个版本同时为 V2 才启用；单边开关保持关闭。
- `PipelineVersionSnapshotV2` 在首次会话任务进入时冻结，后续请求复用同一不可变实例。
- Conversation 层只依赖中立版本快照；配置到快照的映射留在 Harness，未放宽架构依赖矩阵。
- 工厂要求 delegate 与显式注入的五个组件持有同一对象实例；缺失或绑定不一致均失败关闭。
- memory V2 在 production 模式报 `RESEARCH_V2_PERSISTENCE_NOT_READY`；缺 delegate/组件报组合不完整。
- V2 与旧 DeepSeek Web Search gate 同时开启时报 `RESEARCH_V2_LEGACY_SEARCH_FORBIDDEN`。
- PARTIAL 投影成 `RunStatus.SUCCEEDED + degraded_succeeded`，只发既有 `strategy_event`，payload 使用白名单 envelope 并保留 evidence 计数/ID。
- USER_CANCELLED/HARD_DEADLINE 拒绝成功投影，继续由旧取消/超时终态处理。

## 验证证据

```text
X02 工厂/契约/会话/编排组合：359 passed
工厂与依赖规则重点回归：42 passed, 47 subtests passed
全量离线回归：1443 passed, 275 subtests passed, 2 warnings in 45.93s
Ruff：All checks passed
mypy：Success: no issues found in 267 source files
compileall：退出码 0
```

两条警告仍为既有 Starlette 与 Polars 依赖警告。未读取或修改 `.env`，未启动服务，未执行网络、数据库、Git、Java/UI、部署或共享 DDL 操作。

## 边界

- Fake delegate 证明组合根和协议边界可接线，不证明 X01 持久化、真实 ResearchService、真实来源或生产运行已经验收。
- V2 配置保持关闭；任何真实启用仍需 X01/X04/X05 对应授权与证据。
