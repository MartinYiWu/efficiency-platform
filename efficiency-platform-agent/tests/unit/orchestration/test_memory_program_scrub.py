"""只清原run编译程序的本地最后结果，其他run保留。"""
from efficiency_platform_agent.orchestration.builders.conversation_direct import (
    _ConversationDirectProgram,
)
from efficiency_platform_agent.orchestration.registry import GraphRegistry
from efficiency_platform_agent.orchestration.runtime import GraphRuntime


def test_scrub_clears_original_program_last_in_place_and_drops_only_its_run():
    runtime = GraphRuntime(GraphRegistry())
    forgotten, other = _ConversationDirectProgram(None), _ConversationDirectProgram(None)
    forgotten._last["output"] = "synthetic-forget-marker"
    other._last["output"] = "other-run"
    held = forgotten._last
    runtime._programs[("forgotten", "direct")] = forgotten
    runtime._programs[("other", "direct")] = other
    assert runtime.scrub_memory_run("forgotten")
    assert held == {}
    assert ("forgotten", "direct") not in runtime._programs
    assert other._last["output"] == "other-run"
