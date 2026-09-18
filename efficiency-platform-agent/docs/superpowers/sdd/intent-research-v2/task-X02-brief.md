# X02 组合根、会话协议、旧链路兼容与开关任务简报

| 属性 | 内容 |
|---|---|
| 任务 | X02 |
| 状态 | 离线通过 |
| 依赖 | I07、R10；X01 集成阻塞但计划允许 Fake 离线接线 |
| 范围 | Agent 工厂、会话 V2 钩子、版本冻结、V1 投影、默认关闭配置 |

## 不变量

1. V2 默认关闭；Intent 与 Research 必须同时选择 V2 才视为启用。
2. 新任务首次进入时冻结 pipeline、replan、allowlist 与 policy 版本；进行中任务不随全局配置变化。
3. 组合根必须显式注入并绑定同一 SourceRegistry、Tool Runtime、ResearchServiceV2、Intent State Store 与 Research State Store。
4. 内存状态只能用于测试，不能声明生产就绪；生产 V2 必须使用 PostgreSQL 后端且仍受 X01 集成验收约束。
5. V2 启用时禁止同时调用旧 DeepSeek Web Search；未知收费模式不能绕过免费来源准入。
6. PARTIAL 只投影为既有 `strategy_event` 和 `degraded_succeeded`；不得新增 V1 事件名或伪造 confidence。
7. 取消与硬截止继续使用既有 Run 终态路径，不能由 ResearchOutcome 投影成成功。
