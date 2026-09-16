"""验证 S7 预检会显式输出 pypdf 安全状态。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_preflight_reports_pypdf_security_status_without_external_io() -> None:
    """当前锁定的 pypdf 6.x 应在预检中标记为安全状态清晰。"""

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [sys.executable, "scripts/s7_preflight.py", "--gate", "all"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "pypdf_security=clear" in completed.stdout
    assert "pypdf 5.9.0" not in completed.stdout
