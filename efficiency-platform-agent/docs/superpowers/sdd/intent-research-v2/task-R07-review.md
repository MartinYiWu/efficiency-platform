# R07 规格与质量审查

## 审查过程

1. 正文存在轮：验证 URL 存在但没有已保存 SourceDocument 时不能形成证据。
2. 定位轮：覆盖 Unicode 字符区间、hash、excerpt、paragraph_index 和 acquisition_method，任一错配均无效。
3. 身份轮：验证模型只能引用既有 event/evidence，事件外引用、未知引用、陈旧 Brief/Prompt 和重复 proposal 失败关闭。
4. 数字轮：覆盖来源 9/模型 90、numeric_value 与 value_text 不一致，确认数字在证据、Claim 文本和值文本三处绑定。
5. 单位轮：覆盖 percent/seconds 变化，修正短英文单位的子串误命中风险，单位必须在证据和 Claim 文本都出现。
6. 归属轮：官方自述 objective 被拒，announcement/opinion 强制 attributed，inference 强制显式标注。
7. 独立性轮：十篇同稿折为一个 unknown 家族，independent_support_count 为 0；不能多数投票成为客观事实。
8. 原子事实轮：发现仅按主体/单位/时间分组会把准确率与延迟误判冲突，新增 claim_key 参与冲突身份。
9. 冲突轮：不同值双方保留并标 unresolved，不进入 certain_fact；归属式冲突只能作为明确争议交付。
10. 完整性轮：用人工 expected claim keys 计算 recall 并列遗漏，避免把“所有已提 Claim 都有引用”宣传为事实完整。
11. Prompt 安全轮：确认正文作为 USER_UNTRUSTED，经唯一 ContextBuilder 追加；不得生成 URL、改数字/单位或服从网页命令。
12. 边界轮：确认没有质量 COMPLETE、输出渲染、真实模型调用或网络访问，真实来源仍关闭。
13. 回归轮：执行 R07 定向、全仓 Ruff、全 src mypy 和全量 pytest，未发现新增回归。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 已保存正文而非 URL 存在性 | 通过 |
| hash/Unicode span/excerpt/paragraph 交叉校验 | 通过 |
| event/document/evidence 身份门禁 | 通过 |
| 数字、值文本、单位和日期上下文 | 通过 |
| announcement/opinion/inference 归属语义 | 通过 |
| 同稿家族不多数投票 | 通过 |
| 客观 Claim 独立支持门槛 | 通过 |
| 原子 claim_key 冲突分组 | 通过 |
| unresolved 不作为确定事实 | 通过 |
| 人工事实 recall 与遗漏列表 | 通过 |
| 全仓静态检查与全量回归 | 通过 |
| 真实模型、来源和公网事实质量 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R07 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；本结论只覆盖结构化证据定位、Claim 门禁和冲突语义，不代表最终质量、事实完整性、真实模型或公网来源已经验收。
