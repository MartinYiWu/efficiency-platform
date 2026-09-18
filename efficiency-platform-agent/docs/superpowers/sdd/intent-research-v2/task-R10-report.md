# R10 实施报告：结构化交付、输出核验、确定性降级与 V1 适配

## 状态

**离线通过。**

R10 已完成结构化 DeliveryPack、模型草稿 OutputVerifier、安全 Markdown 降级、V1 未核验候选适配，以及 compose/verify 受治理 Prompt。没有启用真实模型或来源、没有发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/delivery.py`
- `src/efficiency_platform_agent/capabilities/research/v2/output_verifier.py`
- `src/efficiency_platform_agent/capabilities/research/v2/renderer.py`
- `src/efficiency_platform_agent/capabilities/research/v2/legacy_adapter.py`
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/research/compose_v2.j2`
- `src/efficiency_platform_agent/prompts/resources/research/verify_v2.j2`
- `tests/unit/capabilities/research_v2/_delivery_support.py`
- `tests/unit/capabilities/research_v2/test_delivery.py`
- `tests/unit/capabilities/research_v2/test_output_verifier.py`
- `tests/unit/capabilities/research_v2/test_legacy_adapter.py`
- `tests/unit/prompts/test_research_v2_templates.py`

## 已实现不变量

- DeliveryPack 固定记录 Brief 摘要、精确时间窗、领域状态、显示状态、请求/交付数量、事件、Claim、Evidence、来源角色、缺口、限制与停止原因。
- Builder 只读取 `ResearchOutcomeV2.usable_event_ids`；未知事件、缺 Claim、断裂引用、未知代表文档和 FAILED 构建均失败关闭。
- unresolved objective Claim 不进入确定性交付；PARTIAL 保持 `degraded_succeeded`，COMPLETE/NO_MATCHES 为 `succeeded`。
- OutputVerifier 拦截 Brief/快照错配、PARTIAL 升 COMPLETE、未请求格式、全网穷尽声明、模型 URL、重复/未知事件、COMPLETE exact 数量不足、未知 Claim、引用断链、事实遗漏和无证据数字篡改。
- 模型草稿只能用 `[evidence:已有ID]`；真实 URL 只由服务端从 Evidence→Document 映射。
- 仅允许一次修复；第二次仍不合格直接 REJECT。COMPLETE exact 数量不足返回 RECOLLECT，但不重置 R09 已消费的补采轮次或预算。
- 生成失败时 `DeliveryPackBuilder + render_markdown` 可直接输出确定性简报，保留结构化事实、来源和限制，不丢研究证据。
- Markdown 对标题、Claim、限制和控制字符转义；服务端 URL 只允许 `http/https` 且必须有 hostname，不原样输出网页 HTML/脚本。
- LegacyResearchAdapter 将 V1 observation 转成 `content_scope=none`、`content_unverified`、coverage unknown 的候选；V1 valid 不升级为 V2 内容已核验。
- compose/verify Prompt 均要求唯一 ContextBuilder、USER_UNTRUSTED、只选已有 ID、禁止 URL/全网声明/状态升级；程序仍是最终裁决者。

## 验证证据

```text
R10 定向 + 既有研究验收：25 passed
全量离线回归：1430 passed, 275 subtests passed, 2 warnings in 43.62s
Ruff：All checks passed
mypy：Success: no issues found in 266 source files
compileall：退出码 0
治理与架构：62 passed, 241 subtests passed
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R10 引入。全仓 formatter 的历史漂移仍按 R09 记录保留；R10 触达文件已执行定向 format。

## 边界与后续

- R10 完成的是离线 Delivery/Verifier/Renderer/Adapter 组件，不代表真实模型生成质量、真实来源 URL 可达性、数据库恢复或端到端 Supervisor 接线已经验收。
- 正式 ModelRuntime、ContextBuilder、Tool Runtime、持久化和组合根接线归 X01—X03；真实模型/来源与灰度回滚归 X04/X05。
- V1 Adapter 只提供显式转换边界；旧 Provider 不被自动启用，收费或准入未知来源仍不得调用。
