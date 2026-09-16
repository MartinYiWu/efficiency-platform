"""验证项目在无 PYTHONPATH 时可以通过 uv 导入源码包。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_project_package_is_importable_without_pythonpath() -> None:
    """干净解释器应从项目安装包导入，而不是依赖测试路径注入。"""

    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import efficiency_platform_agent; "
                "from efficiency_platform_agent.harness.service import "
                "AgentRuntimeService; "
                "from efficiency_platform_agent.orchestration.runtime import "
                "GraphRuntime; "
                "from efficiency_platform_agent.providers.llm.deepseek import "
                "DeepSeekModelProvider; "
                "print(efficiency_platform_agent.__file__)"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "efficiency_platform_agent" in completed.stdout
