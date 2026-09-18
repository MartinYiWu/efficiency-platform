# R05 实施报告：时间/条件过滤与文档级去重

## 状态

**离线通过。**

R05 已完成研究候选规范化、URL 身份保真、时间/来源条件过滤、已验证语义判别消费、文档级精确去重和版本保留。没有调用真实模型、没有启用真实来源或发起公网请求，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_evidence_v2.py`
- `src/efficiency_platform_agent/capabilities/research/v2/normalization.py`
- `src/efficiency_platform_agent/capabilities/research/v2/filtering.py`
- `src/efficiency_platform_agent/capabilities/research/v2/deduplication.py`
- `src/efficiency_platform_agent/prompts/registry.py`
- `src/efficiency_platform_agent/prompts/resources/research/relevance_v2.j2`
- `tests/unit/capabilities/research_v2/test_normalization.py`
- `tests/unit/capabilities/research_v2/test_filtering.py`
- `tests/unit/capabilities/research_v2/test_document_dedup.py`
- `tests/unit/prompts/test_research_v2_templates.py`

## 已实现不变量

- URL 只移除明确跟踪参数与 fragment，保留文章 ID、语言、版本、参数顺序/编码和路径大小写；HTTPS、无用户凭据及标准端口以外的输入失败关闭。
- SourceDocument 保留 candidate/source item/版本、原始与规范 URL、规范正文、hash、提取器、内容范围、原始时间和各类独立时间字段；不以当前时间或抓取时间冒充发布时间。
- 发布时间、更新时间、事件时间、最早首发、首次发现与抓取时间互不替代；无时区、未知时间或部分窗口重叠进入 uncertain，不默认通过。
- 旧闻转载优先使用最早可确认首发时间判定；同 URL 或同 source item 的不同正文 hash 保留为版本，不误合并。
- 过滤固定执行 F0 资源状态、F1 来源/语言/事件地区/来源角色/时间、F2 语义相关性；关键词缺失不参与硬拒绝。
- SemanticRelevanceDecision 必须绑定 document_id、content_hash、brief digest、受治理 Prompt 版本、合法 requirement_ids 和规范正文逐字摘录；未知文档、旧 hash、旧 Brief、旧 Prompt 或伪造摘录均失败关闭为 uncertain 或输入错误。
- 语义 Prompt 只接收可信 Schema 模板变量；实际简报和文档明确要求经唯一 ContextBuilder 作为 USER_UNTRUSTED 数据追加，网页中的越权文字不能改变范围、权限、预算或工具白名单。
- 文档去重匹配顺序为 source item + hash、规范 URL + hash、正文 hash；代表文档稳定按 document_id 选取，重复与唯一数量守恒，重复标识与代表标识不交叉。
- 本任务只形成证据候选，不在此层宣称事件等价、来源独立、Claim 被支持或研究完成。

## 验证证据

```text
R05 定向（规范化/过滤/去重/Prompt）：21 passed
Ruff（全 src/tests）：All checks passed
mypy（全 src）：Success: no issues found in 249 source files
全量回归：1356 passed, 275 subtests passed, 2 existing dependency warnings in 44.85s
```

两条警告仍来自既有 Starlette BlockingPortal 弃用提示与 Polars 未来返回类型提示，不由 R05 引入。

## 边界与后续

- R05 只消费已经过 Schema 校验的语义判别；真实 ModelRuntime 调用、ContextBuilder 组装和图内调度在 R09/X02 组合根接入前保持未启用。
- 正文目前通过稳定 `artifact_ref` 绑定 hash；规范正文持久化、重启恢复和引用快照由 R07/X01 完成。
- 文档级同文去重不等同于事件聚类；转载关系、来源家族、跨语言同稿、事件版本和排序由 R06 实施。
- 真实来源仍全部保持 `enabled=false`、`UNVERIFIED`、`cost_mode=unknown`。
