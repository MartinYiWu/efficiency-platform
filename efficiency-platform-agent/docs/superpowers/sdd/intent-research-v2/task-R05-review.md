# R05 规格与质量审查

## 审查过程

1. URL 身份轮：覆盖文章 ID query、路径大小写、编码参数、标准端口、仅跟踪 query、fragment、HTTP 与 URL 用户凭据，确认不会删除有意义 query 或把不同文章合并。
2. 时间事实轮：覆盖精确带时区时间、仅日期无时区、未知时间、部分区间重叠和旧闻转载，确认不以 now/fetched_at 回填且最早首发优先。
3. 条件轮：验证来源 allow/exclude、语言、事件地区与 primary 角色；未知值进入 uncertain，媒体语言不替代事件地区。
4. 语义轮：验证无主题关键词但同义相关可通过；missing/uncertain/stale 判别均不默认 True。
5. 绑定轮：补齐 Prompt 版本、brief digest、正文 hash、requirement_ids、原文摘录和未知 document_id 的交叉校验，防止旧判定或跨文档判定复用。
6. Prompt 安全轮：确认模板不嵌入网页正文，明确 USER_UNTRUSTED、不得扩范围/预算/工具权限、仅输出固定 Schema，正文后续只能由 ContextBuilder 追加。
7. 去重轮：覆盖 source item、规范 URL、跨 URL 相同正文、同 URL 不同 hash 和文章 ID 差异；代表选择确定、版本保留、数量守恒。
8. 契约轮：补齐 SourceDocument 独立时间字段、原始映射和资源/来源角色；所有 datetime 必须有时区，未知时区不能伪造精确时间。
9. 边界轮：确认模块没有事件聚类、Claim 接受、质量成功或真实模型/网络调用，真实来源配置继续关闭。
10. 回归轮：执行 R05 定向、全仓 Ruff、全 src mypy 和全量 pytest，未发现新增回归。

## 最终确认

| 检查项 | 结果 |
|---|---|
| URL 身份保真与明确 tracking 删除 | 通过 |
| published/updated/event/first_seen/fetched 分离 | 通过 |
| 缺时区/未知/部分重叠不默认通过 | 通过 |
| 旧闻首发时间优先 | 通过 |
| F0/F1/F2 与数量守恒 | 通过 |
| 语义判别全绑定与 Prompt 版本治理 | 通过 |
| 无关键词硬拒绝 | 通过 |
| 文档精确去重与不同 hash 版本保留 | 通过 |
| 全仓静态检查与全量回归 | 通过 |
| 真实模型、来源和公网可用性 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R05 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；本结论只覆盖确定性规范化、过滤与文档级去重，不代表事件级聚类、事实证据、真实模型质量或公网来源已经验收。
