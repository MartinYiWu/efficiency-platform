# X03 全链路离线、攻击与故障验收任务简报

| 属性 | 内容 |
|---|---|
| 任务 | X03 |
| 状态 | 离线通过 |
| 已完成 | 架构守卫、LangGraphResearchServiceV2、Conversation→Intent V2→Supervisor→ToolRuntime→Fake Provider→Delivery 全链、R01—R23 追踪矩阵与四条证据人工核对 |
| 待完成 | X01 真实持久化恢复、X04 真实来源/模型验收、X05 灰度回滚；均不属于 X03 离线通过范围 |

## 已冻结不变量

1. Research Agent/Graph 不得直接使用 HTTP 客户端、socket、OpenAI SDK、feedparser 或 Trafilatura。
2. Research V2 只能构建一个 StateGraph，不创建第二 GraphRuntime。
3. Research V2 orchestration/capability/provider 运行面禁止动态 import；Provider 不得反向依赖 Agent、Orchestration、Harness 或 Conversation。
4. `LangGraphResearchServiceV2` 校验 Policy、Budget Lease、硬截止，调用唯一子图后通过 Materializer 按 ID 恢复结果。
5. 物化结果的 outcome、stop_reason、usable event IDs 与 evidence IDs 必须和 GraphState 一致，否则失败关闭。
6. X03 最终验收仍必须经过真实 ConversationService 和 Supervisor 路径；当前服务级测试不能替代全链路结论。
