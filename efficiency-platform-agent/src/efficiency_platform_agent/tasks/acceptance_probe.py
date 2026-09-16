"""S7 Redis/Taskiq 离线验收探针的输入边界。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class AcceptanceProbeError(ValueError):
    """合成探针输入不满足最小字段约束。"""


_ALLOWED = frozenset({"run_stamp", "task_id", "sequence"})
_STAMP = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


def validate_synthetic_input(value: Mapping[str, Any]) -> dict[str, Any]:
    """只接受 run_stamp、task_id、sequence 三个合成字段。"""
    if not isinstance(value, Mapping):
        raise AcceptanceProbeError("探针输入必须是对象")
    if set(value) != _ALLOWED:
        raise AcceptanceProbeError("探针仅允许 run_stamp、task_id、sequence")
    run_stamp, task_id, sequence = (
        value["run_stamp"],
        value["task_id"],
        value["sequence"],
    )
    if not isinstance(run_stamp, str) or not _STAMP.fullmatch(run_stamp):
        raise AcceptanceProbeError("run_stamp 格式非法")
    if not isinstance(task_id, str) or not task_id.strip():
        raise AcceptanceProbeError("task_id 不能为空")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise AcceptanceProbeError("sequence 必须是正整数")
    return {"run_stamp": run_stamp, "task_id": task_id, "sequence": sequence}


class AcceptanceProbe:
    """离线探针门面，不执行用户函数、文件读取或网络调用。"""

    @staticmethod
    def validate(value: Mapping[str, Any]) -> dict[str, Any]:
        """校验并返回脱敏后的合成输入。"""
        return validate_synthetic_input(value)


__all__ = ["AcceptanceProbe", "AcceptanceProbeError", "validate_synthetic_input"]
