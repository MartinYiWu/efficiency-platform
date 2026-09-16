"""S6 仅内存结构化 Fake，不访问文件、网络或外部系统。"""

from __future__ import annotations

from collections.abc import Mapping

from efficiency_platform_agent.core.run import JsonObject


class ScriptedFakeScenarioRuntime:
    """按场景 ID 返回预置结构化结果。"""

    def __init__(self, scripts: Mapping[str, object] | None = None) -> None:
        self.scripts = dict(scripts or {})
        self.calls: list[str] = []

    async def execute(self, scenario_id: str) -> object:
        self.calls.append(scenario_id)
        return self.scripts.get(scenario_id, JsonObject((("status", "complete"),)))


class ScriptedFakeProvider:
    """只从构造时内存脚本返回结构化值。"""

    def __init__(self, responses: Mapping[str, object] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[str] = []

    async def complete(self, key: str) -> object:
        self.calls.append(key)
        return self.responses.get(key, JsonObject((("status", "ok"),)))


class RecordingFakeTool:
    """只记录无副作用的固定内存查询。"""

    side_effect = False

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(self, key: str) -> JsonObject:
        self.calls.append(key)
        return JsonObject((("lookup", "s6-synthetic"),))


__all__ = ["RecordingFakeTool", "ScriptedFakeProvider", "ScriptedFakeScenarioRuntime"]
