# X03 规格与质量审查

## 审查过程

1. 链路轮：确认入口经过真实 ConversationService、IntentPipelineV2、Supervisor、ResearchService、ToolRuntime 和 Fake Provider，无缩短链路旁路。
2. 身份轮：发现并修正 Supervisor 步骤 ID `research` 覆盖 operation task_id 的问题；Brief 按租户和真实任务标识隔离。
3. 交接轮：发现并修正 Delegate 与图 resolver 使用不同 SubmissionStore 的问题；组合根强制同实例。
4. 时间轮：三轮采集请求只使用同一 UTC 半开昨天窗口，未因 exact 数量不足扩大日期。
5. 停止轮：3+1+0 在两轮补采上限后得到 PARTIAL/ROUND_LIMIT/4，不伪造第 5 条。
6. 输出轮：四个事件均有 Claim、EvidenceRef 和服务端 URL；最终 V1 交付仍保留引用。
7. 普通聊天轮：将本地确定性聊天前置，验证“你好”不调用 V2 或采集。
8. 攻击面轮：AST 守卫禁止 Graph/Agent 直接联网、动态 import、Provider 反向依赖和第二 GraphRuntime；异常 canary 不穿透 Provider adapter。
9. 兼容轮：V2 默认关闭、旧未知收费搜索互斥、共享 SubmissionStore 与 V1 研究回归通过。
10. 全量轮：1458 项回归、270 源码 mypy、源码/测试 Ruff、compileall 和文档治理通过；历史快照 Ruff 漂移单列，不纳入本任务成功宣称。

## 结论

**PASS。** X03 可标记为“离线通过”。R17/R18 的真实未知外部结果和跨进程恢复仍明确归 X01 阻塞；真实来源/模型/费用/网络安全验收归 X04，灰度与回滚归 X05。本审查没有把离线 Fake 或内存状态表述为生产就绪。
