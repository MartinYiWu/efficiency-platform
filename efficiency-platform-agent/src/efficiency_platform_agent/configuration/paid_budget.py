from __future__ import annotations

import os
import sys
from pathlib import Path


def default_paid_budget_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "efficiency-platform" / "paid-budget.sqlite3"
