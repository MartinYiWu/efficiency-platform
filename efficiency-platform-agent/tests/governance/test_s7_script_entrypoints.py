"""验证 S7 脚本在干净解释器环境中的默认关闭入口。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_verify_cli_runs_without_pythonpath_and_keeps_real_gates_closed() -> None:
    """直接运行脚本时应可导入项目包，并保持零外部 I/O。"""

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "scripts/s7_verify.py"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {
        "status": "NOT_EXECUTED",
        "reason": "gate_not_selected",
        "external_io": False,
        "selected_real_gates": [],
    }
