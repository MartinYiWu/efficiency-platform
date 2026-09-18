# I03 实施任务简报：确定性时间解析与口径校验

## 目标与边界

实现纯确定性的 `TemporalResolver`：只接收 C02 的结构化时间表达、显式 anchor 和 IANA timezone，输出冻结的左闭右开 UTC 窗口或稳定 `TIME_AMBIGUOUS` / `TIME_INVALID`。解析器不读取系统时间，不识别业务任务，不调用模型、工具、网络或仓储。

## 文件白名单

- 新增 `src/efficiency_platform_agent/orchestration/intent_v2/temporal.py`
- 更新 `src/efficiency_platform_agent/orchestration/intent_v2/__init__.py`
- 必要时补充 `src/efficiency_platform_agent/contracts/temporal_v2.py` 的明确时间口径字段
- 新增 `tests/orchestration/intent_v2/test_temporal.py`
- 必要时补充契约回归
- 完成后新增 I03 report/review，并更新实施进度账本

## 冻结规则

1. anchor 必须带时区；timezone 必须是有效 IANA 标识；解析过程中不得读取当前系统时间。
2. 所有输出使用 UTC、左闭右开，并保留原 timezone、原文、UTC anchor 和 `published_at` / `updated_at` / `event_at` 口径。
3. 日历日/周/月/季度/年在指定时区按本地边界计算；周一为周起点；DST 日允许真实持续 23 或 25 小时。
4. 滚动小时/日/周按真实持续时间从 anchor 回退；滚动月按同一时区的日历月回退并对月末截断。
5. 自然日期范围的结束日期按整日包含，内部转换为下一本地日的右开边界；带明确时刻的结束值保持精确右开时刻。
6. 日期库只使用显式 RELATIVE_BASE/timezone 解析表达原文；结构与原文冲突、缺年跨年、模糊数量、未指定时间或无界 `before` 不猜测，返回 `TIME_AMBIGUOUS`。
7. 不合法日期、反向/零长度范围、naive anchor、非法 timezone 返回 `TIME_INVALID`；日期库失败后不得回退到当前时间或固定 7 天。
8. 历史热榜是否存在可用历史来源属于后续 SourcePlanner/DecisionPolicy，不由时间解析成功推断。

## 验收

先写昨天、最近 24 小时、上周、自然日期范围、模糊表达、跨年/闰日、DST、非法时区、反向范围、午夜 anchor 和时间口径红灯；实现后执行 I03 定向、I01/I02/C02 回归、架构守卫、Ruff、mypy 和全量测试，并完成独立文件级审查。
