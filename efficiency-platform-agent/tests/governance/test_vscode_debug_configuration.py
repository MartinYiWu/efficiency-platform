"""校验 VSCode 的 pytest 与 F5 调试治理配置。"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_jsonc(path: Path) -> dict:
    """读取允许中文注释的 JSONC 文件。"""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"//[^\r\n]*", "", text)
    return json.loads(text)


def test_settings_use_pytest_for_tests_and_disable_unittest() -> None:
    settings = _load_jsonc(PROJECT_ROOT / ".vscode" / "settings.json")

    assert settings["python.testing.pytestEnabled"] is True
    assert settings["python.testing.unittestEnabled"] is False
    assert settings["python.testing.pytestArgs"] == ["tests"]
    assert settings["python.defaultInterpreterPath"] == (
        r"${workspaceFolder}\.venv\Scripts\python.exe"
    )


def test_launch_contains_governed_agent_and_pytest_debug_profiles() -> None:
    launch = _load_jsonc(PROJECT_ROOT / ".vscode" / "launch.json")
    configurations = launch["configurations"]
    by_name = {item["name"]: item for item in configurations}

    expected_names = {
        "启动：本地真实 Agent API",
        "调试：当前 pytest 测试文件",
        "调试：Agent 全量离线测试",
    }
    assert expected_names <= by_name.keys()

    agent = by_name["启动：本地真实 Agent API"]
    assert agent["request"] == "launch"
    assert agent["module"] == "efficiency_platform_agent"
    assert agent["console"] == "integratedTerminal"

    current_file = by_name["调试：当前 pytest 测试文件"]
    assert current_file["module"] == "pytest"
    assert current_file["args"] == ["${file}", "-q"]
    assert current_file["console"] == "integratedTerminal"

    offline = by_name["调试：Agent 全量离线测试"]
    assert offline["module"] == "pytest"
    assert offline["args"] == ["tests", "-m", "not real_external", "-q"]
    assert offline["console"] == "integratedTerminal"


def test_launch_does_not_contain_secret_like_configuration_values() -> None:
    launch_path = PROJECT_ROOT / ".vscode" / "launch.json"
    launch_text = launch_path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in launch_text
    assert "Authorization" not in launch_text
    assert "postgresql://" not in launch_text
    assert "redis://" not in launch_text
