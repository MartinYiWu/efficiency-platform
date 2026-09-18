from datetime import UTC, datetime

from efficiency_platform_agent.capabilities.research.request_policy import (
    describe_research_constraints,
    has_explicit_source_count,
    has_explicit_time_window,
    official_sources_only,
    requested_source_count,
    resolve_research_window,
)


def test_requested_source_count_reads_explicit_chinese_delivery_count() -> None:
    assert requested_source_count("严格给我3条 AI 新闻", default=1) == 3
    assert requested_source_count("收集今天的 5 条全球 AI 热点", default=1) == 5
    assert requested_source_count("收集最新动态", default=2) == 2
    assert has_explicit_source_count("严格给我3条 AI 新闻")
    assert not has_explicit_source_count("收集昨天的 AI 动态")


def test_resolve_research_window_keeps_explicit_day_without_expansion() -> None:
    now = datetime(2026, 9, 17, 1, 30, tzinfo=UTC)

    window = resolve_research_window("2026年9月16日发生的 AI 新闻", now=now)

    assert window.start == datetime(2026, 9, 15, 16, tzinfo=UTC)
    assert window.end == datetime(2026, 9, 16, 16, tzinfo=UTC)
    assert window.original_text == "2026年9月16日"
    assert has_explicit_time_window("请收集2026年9月16日的AI新闻")
    assert not has_explicit_time_window("请收集最新AI新闻")


def test_official_source_constraint_is_semantic_not_one_fixed_phrase() -> None:
    assert official_sources_only("只接受项目官方博客、论文主页或 GitHub 官方 Release")
    assert official_sources_only("来源必须来自一手官方渠道")
    assert not official_sources_only("给出公开来源链接")


def test_constraint_summary_preserves_explicit_day_and_shortage() -> None:
    summary = describe_research_constraints(
        "严格给我3条2026年9月16日发生的AI新闻",
        requested_count=3,
        delivered_count=2,
        count_required=True,
        now=datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    assert "2026年9月16日" in summary
    assert "目标条数=3" in summary
    assert "有效来源数=2" in summary
    assert "不得扩大时间范围" in summary
    assert "默认窗口不适用" in summary


def test_constraint_summary_uses_best_effort_when_count_is_not_explicit() -> None:
    summary = describe_research_constraints(
        "收集昨天的AI新闻",
        requested_count=5,
        delivered_count=2,
        count_required=False,
        now=datetime(2026, 9, 17, 1, 30, tzinfo=UTC),
    )

    assert "条数策略=best_effort" in summary
    assert "目标条数=5" not in summary
