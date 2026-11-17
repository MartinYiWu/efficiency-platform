"""旧付费入口必须在读取配置、构造客户端和联网前拒绝。"""

from __future__ import annotations

import importlib
import inspect
import socket
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "module_name,function_name",
    [
        ("intent_v2_evaluate", "execute_live_evaluation"),
        ("research_v2_acceptance", "execute_direct_local_acceptance"),
        ("research_v2_canary", "execute_canary"),
        ("research_v2_cluster_evaluate", "execute_cluster_evaluation"),
        ("s7_verify", "run_deepseek_chat_acceptance"),
        ("s7_verify", "probe_deepseek_web_search"),
        ("s7_verify", "run_deepseek_web_search_acceptance"),
    ],
)
async def test_legacy_paid_entry_is_disabled_before_any_io(module_name, function_name):
    module = importlib.import_module(f"scripts.{module_name}")
    function = getattr(module, function_name)
    kwargs = {
        name: Path("nonexistent")
        for name, parameter in inspect.signature(function).parameters.items()
        if parameter.default is inspect.Parameter.empty
    }
    if "run_count" in inspect.signature(function).parameters:
        kwargs["run_count"] = 3
    with (
        patch(
            "openai.AsyncOpenAI", side_effect=AssertionError("bare client forbidden")
        ),
        patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        ),
        patch.object(
            Path,
            "read_text",
            side_effect=AssertionError("configuration read forbidden"),
        ),
        pytest.raises(RuntimeError, match="^PAID_LEGACY_ENTRY_DISABLED"),
    ):
        await function(**kwargs)
