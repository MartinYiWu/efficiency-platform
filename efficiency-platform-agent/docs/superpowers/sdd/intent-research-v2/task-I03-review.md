# I03 规格与质量审查

## 审查范围

审查覆盖 I03 计划、任务简报、时间契约、Resolver、测试与报告。项目规范禁止 Git，因此以当前文件、反例和新鲜测试输出进行文件级审查；未调用网络、模型、研究工具或数据库。

## 审查过程

审查采用与实现阶段分离的三轮反例驱动：

1. 核心口径轮：验证昨天/最近 24 小时、上周、自然日期范围、闰日、跨年、DST、非法时区、反向范围、午夜 anchor 和 basis。
2. 结构冲突轮：发现并修复冲突日期别名、多个时长数字、绝对月份、时刻继承、裸数字日期及 before/after 关系词冲突。
3. 缺年轮：发现并修复部分缺年跨年、缺年未来 after 的错误分类，确保需要用户确认的情况返回 `TIME_AMBIGUOUS` 而非猜年或误报非法。

以上问题均在 I03 内修复并增加回归。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 显式 aware anchor、IANA timezone、无系统时钟读取 | 通过 |
| 日历窗口与滚动窗口分离 | 通过 |
| 周一周界、整日包含与左闭右开 UTC | 通过 |
| DST 23/25 小时日、闰日、跨年、午夜 | 通过 |
| 原文与结构字段冲突检测 | 通过 |
| 模糊数量、未指定、无界 before 不猜测 | 通过 |
| 缺年跨年/未来边界返回 TIME_AMBIGUOUS | 通过 |
| 非法日期/时区/anchor/显式反向范围返回 TIME_INVALID | 通过 |
| published_at/updated_at/event_at 口径可序列化回读 | 通过 |
| dateparser 显式 RELATIVE_BASE/timezone，无 now/7 天回退 | 通过 |

## 新鲜验证

```text
I03 定向：28 passed
意图 V2 + contracts + architecture：216 passed, 124 subtests passed
全量回归：1155 passed, 275 subtests passed, 2 existing dependency warnings
Ruff：All checks passed
mypy：Success, 3 source files
```

## 结论

**PASS。** 未发现遗留的 Critical、Important 或 Minor 问题。I03 可标记为“离线通过”。该结论仅覆盖确定性时间语义，不代表真实来源具有历史数据，也不代表后续解释器、能力绑定或研究闭环已经完成。
