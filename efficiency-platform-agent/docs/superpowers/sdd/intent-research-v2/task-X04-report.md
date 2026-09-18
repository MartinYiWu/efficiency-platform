# X04 阶段报告：真实来源、模型与五类请求验收

| 属性 | 内容 |
|---|---|
| 状态 | 真实验收通过（Agent 侧受控范围） |
| 验收日期 | 2026-09-17 |
| 模型 | `deepseek-v4-flash` |

## 来源准入

只读预检通过 3 个免费公开来源：Google Blog RSS、LangGraph GitHub Releases Atom、Hacker News API。实际探测均为 HTTP 200 且顶层 Schema 合格；安全传输固定解析 IP、保留原 Host/SNI/证书校验、禁环境代理并限制响应体。arXiv 与 GDELT 仍为 `UNVERIFIED + disabled`，没有为凑数调用。

## 真实模型三轮评测

冻结数据集 `2026-09-16.1` 共执行 3 个独立 run、18 次真实模型调用。逐轮指标：

| 轮次 | 关键字段 | READY 精确率 | 完整请求覆盖 |
|---|---:|---:|---:|
| 1 | 100% | 100% | 100% |
| 2 | 100% | 100% | 100% |
| 3 | 95.10% | 100% | 100% |

第三轮保留 7 个攻击样本的 `safe_error` 差异，没有择优隐藏。底层 DeepSeek Provider 已修复内部 `logical_model` 参数误传 SDK 的问题，并对 400/403/404/422 做稳定状态归一化。

## 五类真实请求

真实来源与模型均在 X01 PostgreSQL 父 BudgetLease 下执行。结果见 `task-X04-live-five-case-acceptance.json`：

- 昨天 AI 新闻：PASS，严格时间窗内 1 条，引用覆盖 100%。
- 上周指定主题：PARTIAL，当前免费源窗口内无匹配事件；不扩窗、不编造。
- 精确 5 条：PARTIAL，实际 4 条；明确不足，引用覆盖 100%。
- 基于前文改写公众号：PASS，5 条来源可定位，引用覆盖 100%。
- 普通聊天：PASS，模型调用发生、来源调用为 0。

Google Feed 1 次、GitHub Atom 1 次、HN 13 次请求均无传输错误。实际 Usage 已记录；Provider 没有返回货币成本，所以 `used_cost_microunits=0 / cost_observed=false` 只表示费用不可观测，不能解释为免费。

## 事件聚类量化

冻结 manifest 通过 `research-cluster-benchmark/1` 确定性展开为 100 篇合成文档、30 个 gold 事件；每个模型 bucket 同时包含同公司、同版本、同一天的产品发布与服务故障，模型输入不含 gold event ID。`deepseek-v4-flash` 对 15 个 bucket 做真实盲聚类：预测 30 个事件，pairwise gold/predicted 均为 120 pair，precision=100%、recall=100%、误合并 0、漏合并 0。输入/输出 token 为 9432/10649；Provider 未返回货币成本。

工件见 `task-X04-live-cluster-evaluation.json`，固定 corpus SHA-256 为 `312156481f67c34e9c4632035f95f11dfb9a487a12dfcbbe1b96300b9c814ddb`。标签来自确定性 fixture 构造而非人工标注，`human_missed_count=null`，并明确 `statistical_significance_claimed=false`；结果只证明冻结合成基准达标，不外推真实世界绝对精度。X04 计划门槛据此关闭，但仍未部署生产流量。
