# R10 结构化交付、输出核验、确定性降级与 V1 适配任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R10 |
| 状态 | 进行中 |
| 依赖 | R07、R08、R09、I06 离线通过 |
| 范围 | Agent 侧 DeliveryPack、OutputVerifier、安全 Markdown、V1 候选适配与 Prompt |

## 不变量

1. DeliveryPack 必须携带 Brief 摘要、精确时间窗、领域状态、请求/交付数量、事件、Claim、Evidence、来源角色、缺口和停止原因。
2. 只能交付 Quality 判定可用的事件；unresolved objective Claim 不得进入确定性产物。
3. 模型只能选择已有 event_id、claim_id、evidence_id，不得生成 URL；真实 URL 由服务端从 document_id 映射。
4. OutputVerifier 必须拦截编造 URL/Claim、引用断链、重复事件、exact 数量不足、全网穷尽声明和 PARTIAL 升 COMPLETE。
5. 仅格式/措辞问题最多修复一次；第二次仍失败则拒绝，不能无限重渲染或重新获得补采预算。
6. 生成失败但已有合格研究事实时，必须以确定性 Markdown 降级，保留全部结构化证据；用户要求模型成稿而未满足时显示 degraded_succeeded。
7. Markdown 必须转义来源标题、Claim 与限制文本，不允许网页 HTML/脚本直接进入产物。
8. COMPLETE 与 NO_MATCHES 映射 succeeded；PARTIAL 且有可用交付映射 degraded_succeeded；FAILED 不得构建成功交付。
9. V1 ResearchResult 只能转为 content_scope=none、content_unverified 的候选；不得把 V1 valid/quality 状态升级成 V2 内容已核验。
