# I06 规格与质量审查

## 审查范围

审查覆盖 I06 计划、任务简报、ResearchBrief 契约扩展、Builder、场景投影、缓存资格、测试与报告。项目规范禁止 Git，因此以当前文件、反例和新鲜测试输出进行文件级审查；未调用真实模型、网络、来源、工具或数据库。

## 审查过程

1. 无损桥接轮：验证小红书来源与公众号目标分离、昨天窗口、exact3、排除项、实体和未知来源 ID 保留。
2. 信任边界轮：验证 task 不匹配、未决引用、阻塞歧义、研究候选歧义、revision0 和缺时间全部失败关闭。
3. 兼容与完整性轮：发现硬需求字段破坏 C02 旧 Brief 构造，改为旧快照可读、Builder 新产物完整且契约重算摘要防篡改。
4. 场景轮：验证多目标/依赖/参数无损，且未知能力、依赖丢失、不完整计划和未就绪 Frame 均无部分步骤。
5. 缓存轮：验证输出格式变化可复用，租户/许可/TTL/主题实体/时间/来源任一不满足即失败关闭。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 来源平台与输出平台独立保存 | 通过 |
| 时间窗非空且复用 I03 解析器 | 通过 |
| exact 数量、排除项、默认诊断无损 | 通过 |
| 可信身份/预算不从 Frame 或参数读取 | 通过 |
| 硬需求 ID/digest 稳定且防篡改 | 通过 |
| intent revision/scope hash/策略版本进入 Brief | 通过 |
| 多目标场景投影不压平、不伪造 V1 | 通过 |
| 不支持/不完整场景无部分步骤 | 通过 |
| 缓存同租户/许可/TTL/事实范围/来源全覆盖 | 通过 |
| C02 旧 Brief、I03/I05/旧场景与架构无回退 | 通过 |

## 新鲜验证

```text
I06 + ResearchBrief 契约：26 passed
I03/I05/旧场景组合：86 passed
意图 V2 + contracts + architecture：265 passed, 124 subtests passed
全量回归：1210 passed, 275 subtests passed, 2 existing dependency warnings
Ruff：All checks passed
mypy：Success, 10 source files
```

## 结论

**PASS。** 未发现遗留的 Critical、Important 或 Minor 问题。I06 可标记为“离线通过”。该结论不代表 I07 会话/CAS 接线、真实来源采集、缓存持久化或真实模型精度已经完成。
