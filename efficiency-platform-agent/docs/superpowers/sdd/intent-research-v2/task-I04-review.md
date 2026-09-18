# I04 规格与质量审查

## 审查范围

审查覆盖 I04 计划、任务简报、解释器、Context/Intent 契约变化、Prompt 注册与模板、测试和报告。项目规范禁止 Git，因此以当前文件、反例和新鲜测试输出进行文件级审查；未调用真实模型、网络、研究工具或数据库。

## 审查过程

审查采用多轮反例驱动：

1. 调用边界轮：验证首次合法、一次修复、两次失败、Provider 超时、预算不足、取消、一次复核及三次上限。
2. 架构边界轮：冻结端口只含引用，不能直接构造身份和预算；通过受信任 resolver 适配后仍强制复用 ContextBuilder/ModelRuntime，真实接线留给 I07。
3. 审计与失败轮：补齐错误路径的 catalog/context/lease 版本、Prompt 未注册失败关闭、20,000 字符裁剪与小预算动态输出上限。
4. 语义复核轮：无效复核保留合法 Patch，复核不得增加未决引用，revision 修复得到可信期望值。
5. 消息溯源轮：发现当前正文没有唯一可信 message_id；补充 `current_message_id ∈ visible_message_ids` 且 visible IDs 唯一/有界约束。

以上问题均在 I04 内修复并增加回归。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 冻结 interpret 端口未改签名 | 通过 |
| 唯一 ContextBuilder、现有 PromptRuntime/ModelRuntime | 通过 |
| 当前正文与 current_message_id/可见范围绑定 | 通过 |
| 首次/修复/复核总调用上限及无循环 | 通过 |
| 每次调用刷新 lease 额度并扣除实际 attempts/usage | 通过 |
| Provider/预算/取消/Context/Prompt 技术错误不转澄清 | 通过 |
| Prompt 显式注册、可信/不可信数据分区 | 通过 |
| 修复输出安全裁剪、无异常正文泄露 | 通过 |
| review 不依赖 confidence、不恶化未决引用 | 通过 |
| usage/model/prompt/catalog/context/lease 审计事实 | 通过 |
| 身份聊天、按钮说明、否定研究无工具调用 | 通过 |
| V1 解释器与既有 Prompt/Context 行为不回退 | 通过 |

## 新鲜验证

```text
I04 定向：21 passed
V1/PromptRuntime/ContextBuilder 回归：61 passed
意图 V2 + contracts + architecture：234 passed, 124 subtests passed
全量回归：1176 passed, 275 subtests passed, 2 existing dependency warnings
Ruff：All checks passed
mypy：Success, 4 source files
```

## 结论

**PASS。** 未发现遗留的 Critical、Important 或 Minor 问题。I04 可标记为“离线通过”。该结论不代表真实模型准确率、真实 Context/租约接线、能力授权或端到端会话生命周期已经完成。
