# I07 规格与质量审查

## 审查范围

审查覆盖 I07 计划、任务简报、Pipeline、InMemory 仓储、ConversationService 注入点、评测器、240 例资产、测试与报告。项目规范禁止 Git，因此以当前文件、反例和新鲜测试输出进行文件级审查；未调用真实模型、网络、来源、工具或数据库。

## 审查过程

1. 顺序与门禁轮：确认 I01— I06 唯一实现按固定顺序组装，commit 之前无 dispatch，失败/澄清/不支持均无工具资格。
2. 并发与幂等轮：验证同消息重放不重复解释、同 ID 异文冲突、不同消息同 revision 仅一个 CAS 成功。
3. 租户与提交真实性轮：发现 task-only 键和提前 committed，改为租户复合键并由仓储在锁内生成 committed 结果。
4. Run 生命周期轮：修复 WAITING_INPUT Brief 的 Run 绑定；验证终态新 Run、运行中安全边界替换、取消走既有入口、澄清两轮上限。
5. V1 共存轮：验证只有无 V1 pending 的新任务可调用 V2 hook，返回 None 时 V1 完整回退，未向 V1 fast path 加关键词。
6. 数据集轮：验证 240 总数、类别/拆分、SHA-256、跨 split 语义族隔离、时区、密钥扫描、冻结集禁调参及显式分子/分母指标。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 固定流水线顺序与唯一 I01— I06 实现 | 通过 |
| CAS 前不可派发，冲突不覆盖 | 通过 |
| tenant/task/message 复合隔离 | 通过 |
| 幂等重放不重复模型调用/派发 | 通过 |
| WAITING_INPUT 同 Run、终态新 Run | 通过 |
| 运行中 refine 仅安全边界替换意图 | 通过 |
| cancel 不旁路既有取消入口 | 通过 |
| V1 pending 固定且 fast path 未扩展 | 通过 |
| 240 例计数/hash/语义族/冻结策略 | 通过 |
| 指标含分子分母和逐字段错误 | 通过 |
| 旧会话 API、contracts、场景与架构无回退 | 通过 |

## 新鲜验证

```text
I07 定向：15 passed
I07 + orchestration + conversation + architecture：323 passed, 124 subtests passed
contracts + 场景 Registry + 会话 API：98 passed
全量回归：1225 passed, 275 subtests passed, 2 existing dependency warnings
Ruff：All checks passed
mypy：Success, 18 source files
```

## 结论

**PASS。** 未发现遗留的 Critical、Important 或 Minor 问题。I07 可标记为“离线通过”。该结论不代表真实数据库接线、生产开关、真实模型精度、真实来源采集或灰度发布已经完成。
