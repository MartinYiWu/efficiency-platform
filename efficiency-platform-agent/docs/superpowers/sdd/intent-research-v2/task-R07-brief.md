# R07 Claim 提取、原文定位与冲突管理任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R07 |
| 状态 | 离线通过 |
| 依赖 | R06、C03 离线通过 |
| 范围 | Agent 侧 Claim 提案校验、规范正文字符定位、数值/单位/归属门禁与冲突保留 |

## 不变量

1. URL 存在不能证明内容存在；证据必须绑定已保存 SourceDocument、正文 hash、Unicode 字符区间、逐字 excerpt 和 acquisition_method。
2. EvidenceRef 的偏移只针对规范 `SourceDocument.text`，不使用 HTML 字节偏移；document_id/hash/span/excerpt 任一不一致即无效。
3. 模型只引用服务端已生成的 event_id、document_id 和 evidence_id；真实 URL 由服务端文档映射，不允许模型生成 URL。
4. Claim 类型固定区分 announcement/reported_fact/measured_result/opinion/inference；数值 Claim 必须保留主体、规范数值、单位和日期。
5. 程序校验数字与单位确实出现在支持摘录中；“来源写 9，模型写 90”或单位变化均不得接受。
6. 官方公告只证明发布者宣布/声称了什么；announcement/opinion 必须明确 attributed，inference 必须明确标注 inference，不得写成客观领先事实。
7. 同一通稿家族的十篇转载只算一个来源族，不通过多数投票提升真实性；客观自述若无独立佐证失败关闭。
8. 冲突必须保留双方 Claim 与证据；同事件、主体、时间和单位下的不同值形成 unresolved，不能作为确定事实交付，但可明确归属地陈述争议。
9. 规范正文经唯一 ContextBuilder 作为 USER_UNTRUSTED 数据提供；网页中的提示注入不能改变 brief、权限、预算、Prompt 或工具白名单。
10. 程序引用覆盖率不等于事实完整率；冻结人工预期 claim key 计算 recall 并列出遗漏，不能宣称 100% 真实。
