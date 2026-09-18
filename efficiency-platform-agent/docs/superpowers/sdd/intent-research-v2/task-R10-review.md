# R10 规格与质量审查

## 审查过程

1. 结构包轮：检查时间窗、状态、数量、事件、Claim、Evidence、来源角色、缺口与 stop_reason 均可审计。
2. 可用事件轮：未知事件、无 Claim 事件、断裂 Evidence/Document 和 FAILED 研究均不能构建成功包。
3. 冲突轮：unresolved objective Claim 被排除，不能以确定事实进入交付。
4. 引用轮：模型只能使用 evidence_id token，真实 URL 由服务端映射；假 URL 和引用断链均被拦截。
5. 事实轮：Canonical Claim 文本缺失或数字从 9 篡改为 90 时标记 unsupported。
6. 数量轮：COMPLETE exact 数量不足返回 RECOLLECT；PARTIAL 不被升级为 COMPLETE。
7. 范围轮：全网、全部来源和穷尽声明失败；NO_MATCHES 只陈述已声明的检查范围。
8. 修复轮：第一次可 REVISE，第二次仍失败转 REJECT，避免无限重渲染。
9. 降级轮：模型生成失败仍能从已核验事实生成 Markdown，并保留事件、Claim、Evidence 和局限。
10. 注入轮：HTML、反引号、Markdown 控制字符转义；非 HTTP(S) 服务端 URL 拒绝。
11. V1 轮：VALID observation 仍只得到 `content_unverified` 候选，coverage 保持 unknown。
12. Prompt 轮：compose/verify 禁止生成 URL、扩大范围、改变状态或直接宣布完成。
13. 回归轮：执行 25 项定向/验收、1430 项全量、全仓 Ruff、266 源码 mypy、compileall 与 62 项治理/架构测试。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 结构化 DeliveryPack 与精确范围 | 通过 |
| 可用事件/Claim/Evidence 服务端门禁 | 通过 |
| URL 只由服务端映射 | 通过 |
| 数字、引用、重复与状态升级拦截 | 通过 |
| exact 数量与 PARTIAL 语义 | 通过 |
| 一次修复上限 | 通过 |
| 确定性 Markdown 降级 | 通过 |
| HTML/Markdown/URL 安全渲染 | 通过 |
| V1 不升级 V2 验证状态 | 通过 |
| compose/verify Prompt 治理 | 通过 |
| 全量离线回归与静态门禁 | 通过 |
| 真实模型、来源、数据库与端到端 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R10 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题。该结论只覆盖离线交付构建、确定性核验、降级渲染和 V1 候选适配，不代表真实模型生成、真实来源可达性或生产接线已经验收。
