# I03 实施报告：确定性时间解析与口径校验

## 状态

**离线通过。**

本任务只实现 Agent 侧显式锚点驱动的确定性时间解析；未读取系统时间，未调用网络、真实模型、研究工具或数据库，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/orchestration/intent_v2/temporal.py`
- `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- `src/efficiency_platform_agent/contracts/temporal_v2.py`
- `tests/orchestration/intent_v2/test_temporal.py`
- `docs/superpowers/sdd/intent-research-v2/task-I03-brief.md`
- 本报告与规格/质量审查记录

## 已实现边界

- `TemporalResolver.resolve(expression, anchor, timezone)` 只使用显式 aware anchor 和有效 IANA timezone；不读取当前系统时间。
- 所有输出统一为 UTC 左闭右开窗口，并保留原 timezone、原文、UTC anchor 与 `published_at` / `updated_at` / `event_at` 口径。
- 日历日、周、月、季度、年按本地边界计算，周一起始；“昨天”与“最近 24 小时”严格分开。
- DST 本地日按真实日历边界生成，覆盖 23 小时和 25 小时日；闰日、跨年和午夜 anchor 有固定回归。
- 滚动小时/日/周按真实持续时间回退；滚动月按同一时区日历月回退并在月末截断。
- 自然日期范围包含完整结束日，内部转为下一本地日右开边界；精确时刻范围支持结束时刻继承开始日期。
- 结构字段必须与原文一致；冲突日期词、多个冲突时长、关系词冲突、裸日期数字、模糊数量、未指定表达及无界 before 不猜测，返回 `TIME_AMBIGUOUS`。
- 非法日期、显式反向范围、naive anchor、非法 IANA timezone 和明确未来 after 边界返回 `TIME_INVALID`。
- 缺年导致跨年或未来/过去归属不唯一时返回 `TIME_AMBIGUOUS`，不自动选择某一年。
- dateparser 只在显式 RELATIVE_BASE 与 timezone 下解析输入原文；解析失败不回退到当前时间或固定 7 天。

## 红灯证据

首次只加入核心行为测试后执行：

```text
ModuleNotFoundError: No module named 'efficiency_platform_agent.orchestration.intent_v2.temporal'
```

首轮实现转绿后进行反例审查，新增测试暴露 6 项失败：绝对月份不能解析、冲突日期词未拒绝、多个时长数字未拒绝、结束时刻不能继承日期、裸数字被当作日期、before/after 关系词冲突未拒绝。修复后 25 项通过。

第二轮缺年审查又暴露 2 项错误分类：部分缺年跨年与缺年未来 after 被判为 `TIME_INVALID`，实际应澄清为 `TIME_AMBIGUOUS`。修复后 28 项通过。

## 绿灯与回归证据

```text
I03 定向：28 passed

意图 V2 + contracts + architecture：
216 passed, 124 subtests passed

Ruff：All checks passed

mypy：Success: no issues found in 3 source files

全量回归：
1155 passed, 275 subtests passed, 2 existing dependency warnings in 35.91s
```

运行时版本：Python 3.13.15、dateparser 1.4.3、tzdata 2026.3。两条全量警告来自既有 Starlette `BlockingPortal` 弃用提示和 Polars `read_excel` 未来返回类型变化，不由 I03 引入。

## 未宣称事项

- 时间窗口解析成功不代表目标来源支持历史查询，也不允许用当前榜单替代历史榜单；该能力判断属于后续 SourcePlanner/DecisionPolicy。
- “最近几天”的 7 天默认必须由后续受信任策略以 default provenance 提供；I03 不把模型猜测伪装成用户明确范围。
- I03 未执行真实模型、多来源采集、数据库持久化、端到端 API 或生产时区数据升级验收。
