"""意图 V2 测试 case 的显式注册表。"""

from __future__ import annotations

from typing import Final

INTENT_V2_CASES: Final[dict[str, dict[str, object]]] = {
    "new_task_with_two_goals": {
        "text": "收集 AI 新闻并生成摘要",
        "dialog_act": "new_task",
        "goal_count": 2,
    },
    "refine_clears_platform": {
        "text": "不要公众号了，保留小红书",
        "dialog_act": "refine",
        "clears": "target_platforms",
    },
}


def intent_v2_case(case_id: str) -> dict[str, object]:
    """按显式 ID 读取用例；未知 ID 必须暴露错误。"""

    return INTENT_V2_CASES[case_id]


__all__ = ["INTENT_V2_CASES", "intent_v2_case"]
