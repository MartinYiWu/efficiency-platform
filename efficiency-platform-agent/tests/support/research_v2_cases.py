"""研究 V2 测试 case 的显式注册表。"""

from __future__ import annotations

from typing import Final

RESEARCH_V2_CASES: Final[dict[str, dict[str, object]]] = {
    "count_exact_three": {
        "mode": "exact",
        "target": 3,
        "minimum": 3,
    },
    "partial_after_no_gain": {
        "outcome": "PARTIAL",
        "stop_reason": "NO_GAIN",
    },
}


def research_v2_case(case_id: str) -> dict[str, object]:
    """按显式 ID 读取用例；未知 ID 不返回默认成功。"""

    return RESEARCH_V2_CASES[case_id]


__all__ = ["RESEARCH_V2_CASES", "research_v2_case"]
