# X04 规格与质量审查

## 审查结果

1. 授权与预算：可信本地授权、租户/动作/用例/有效期和非零预算在外部调用前校验；X01 PostgreSQL 是权威父 BudgetLease。
2. 来源：Google RSS、LangGraph Atom、HN API 实际 HTTP 200/Schema 合格；arXiv/GDELT 禁用；未准入和收费未知调用为 0。
3. Intent：同一模型/Prompt/数据集三轮独立 run，18 次调用；逐轮关键字段、READY 精确率、完整覆盖均达标，错误样本完整保留。
4. 五类链路：均真实执行；严格时间窗不足时 PARTIAL，正式事实引用 100%，普通聊天不采集。
5. 聚类：冻结合成基准 100 文档/30 事件，15 次真实模型调用；120/120 predicted/gold pair，precision/recall 100%，0 误合并、0 漏合并。
6. 防作弊：模型输入不含 gold event ID；每个 bucket 同时放入应合并的转载与不应合并的发布/故障；漏文档、重复或未知文档失败关闭。
7. 诚实边界：标签来自确定性 fixture 构造，不是人工标注；无人工作为 gold 漏检统计，报告 `human_missed_count=null`、`statistical_significance_claimed=false`。

## 结论

**PASS（Agent 侧受控真实验收）。** X04 计划门槛全部具备对应证据。结论不等于生产部署，也不把合成聚类基准外推为真实世界绝对精度。
