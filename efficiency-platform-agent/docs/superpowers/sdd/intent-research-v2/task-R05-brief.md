# R05 时间/条件过滤与文档级去重任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R05 |
| 状态 | 离线通过 |
| 依赖 | R04、I06 离线通过 |
| 范围 | Agent 侧文档规范化、严格时间判定、已验证语义判别消费与文档版本去重 |

## 不变量

1. URL 只移除明确跟踪参数和 fragment，保留文章 ID、版本、语言等有意义 query，不改变路径大小写。
2. 文档保留 source item、原始 URL、规范 URL、正文 hash、版本、原始时间及提取映射；同 URL 不同 hash 不合并。
3. published/updated/event/first-seen/fetched 分开；缺失、无时区和部分时间区间重叠均为 UNKNOWN，不以 now/fetched_at 回填发布时间。
4. 旧闻转载以最早可确认首发时间判定；实质更新保留独立版本，不靠新抓取时间进入窗口。
5. 过滤顺序固定为资源安全、可判定硬条件、已验证语义相关；关键词缺失不能直接判无关，uncertain 不默认通过。
6. 语义判别必须绑定 brief digest、document content hash、requirement_ids、Prompt 版本和原文摘录；纯函数不直接调用模型。
7. 文档级去重按 source item、规范 URL、正文 hash 建立身份与版本关系；重复映射和数量必须守恒且确定性稳定。
8. 本任务不做事件聚类、来源独立性、Claim/Evidence 接受或真实模型调用；这些分别属于 R06/R07 及后续组合根。
