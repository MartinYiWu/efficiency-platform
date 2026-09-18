# X04 任务简报：逐源准入、真实模型评测与真实请求验收

| 属性 | 内容 |
|---|---|
| 状态 | 真实验收通过（Agent 侧受控范围） |
| 负责人 | Agent 端维护负责人 |
| 验收日期 | 2026-09-17 |
| 适用范围 | Agent 侧受控来源预检、模型评测与研究验收 |

## 目标与边界

使用可信授权、非零预算和 X01 PostgreSQL 父 BudgetLease，完成来源只读准入、Intent V2 三轮独立真实评测和五类真实请求。原始响应仅进入本地忽略目录；正式文档只保存脱敏 Usage、状态、来源定位和错误样本。不得调用收费未知或未准入来源，不自动注册账户，不修改生产配置、Java/UI 或共享数据库。

## 已执行

- Google Blog RSS、LangGraph Releases Atom、HN API 三类来源探测并 VERIFIED；arXiv/GDELT 保持禁用。
- `deepseek-v4-flash` 三轮共 18 次真实调用，三项 Intent 指标逐轮达标并保留全部错误样本。
- 昨天、上周主题、精确 5 条、前文改写、普通聊天五类真实链路完成；信息不足返回 PARTIAL，不扩窗或编造。

事件聚类使用冻结 manifest 展开为 100 文档/30 事件的确定性合成盲测，真实模型执行 15 个混合 bucket，pairwise precision/recall 均为 100%。该结果不含人工标签，也不声称统计显著性或真实世界同等精度。详细证据见 [X04 报告](task-X04-report.md)。
