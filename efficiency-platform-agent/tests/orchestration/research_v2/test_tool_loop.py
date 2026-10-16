"""LLM 驱动、程序治理的 Research Tool Loop。"""

from __future__ import annotations

import json

import pytest

from efficiency_platform_agent.contracts.research_tooling import (
    EvidencePackV1,
    ResearchRequestV2,
)
from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ExecutionBudget,
    JsonObject,
    ProviderMessage,
    ProviderResult,
    ProviderToolCall,
    ProviderUsage,
    ToolError,
    ToolResult,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.orchestration.research_v2.tool_loop import (
    ResearchToolLoop,
    ResearchToolLoopError,
)
from efficiency_platform_agent.prompts.contracts import (
    AssembledPrompt,
    ModelPolicy,
    OutputContract,
    PromptMessage,
)


class _Assembler:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def assemble(self, **kwargs):
        self.keys.append(kwargs["prompt_key"])
        return AssembledPrompt(
            kwargs["prompt_key"],
            "1.0.0",
            (
                PromptMessage("system", "只使用工具返回的来源"),
                PromptMessage("developer", "保持来源、主张和热点引用闭包"),
                PromptMessage("user", "研究请求和工具结果已隔离"),
            ),
            ModelPolicy(
                1,
                "research-agent",
                "1.0.0",
                "deepseek",
                "deepseek-chat",
                0.2,
                None,
                24000,
                6000,
                5000,
                30000,
                1,
                8,
                "a" * 64,
            ),
            OutputContract(
                1,
                "evidence-pack",
                "1.0.0",
                EvidencePackV1.model_json_schema(),
                "证据包字段",
                "b" * 64,
            ),
            "c" * 64,
            80,
        )


class _ModelRuntime:
    def __init__(self, messages: tuple[ProviderMessage, ...]) -> None:
        self.messages = list(messages)
        self.calls = []

    async def complete(self, demand, request, *, remaining_budget):
        self.calls.append((demand, request, remaining_budget))
        message = self.messages.pop(0)
        result = ProviderResult(
            "research-agent/1",
            message,
            ProviderUsage(10, 5, 0, 0, 0),
        )
        candidate = ModelCandidate(
            "research",
            "fake",
            "fake-model",
            ModelTier.STRONG,
            True,
            True,
            100_000,
            True,
            False,
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "selected"),),
            UsageSnapshot(10, 5, 0, False),
            False,
        )


class _Executor:
    def __init__(self, results: dict[str, ToolResult]) -> None:
        self.results = results
        self.calls: list[ProviderToolCall] = []

    async def invoke(self, call, request, allowed_tools, budget):
        del request, allowed_tools, budget
        self.calls.append(call)
        return self.results[call.tool_call_id]


def _request() -> ResearchRequestV2:
    return ResearchRequestV2(
        request_id="research-1",
        tenant_id="tenant-1",
        user_id="user-1",
        run_id="run-1",
        topic="最近 7 天 AI 行业热点",
        date_range="最近7天",
        source_ids=("github-releases", "hacker-news"),
        language="zh-CN",
        max_results=10,
    )


def _budget(*, calls: int = 4, iterations: int = 6) -> ExecutionBudget:
    return ExecutionBudget(iterations, calls, 100_000, 20_000, 60_000, 1_000_000)


def _call(
    call_id: str = "call-1",
    *,
    name: str = "research.discover.v2",
    query: str = "AI releases",
    url: str | None = None,
) -> ProviderToolCall:
    values: tuple[tuple[str, object], ...] = (("query", query),)
    if url is not None:
        values = (*values, ("url", url))
    return ProviderToolCall(
        call_id,
        name,
        JsonObject(tuple((key, value) for key, value in values)),
    )


def _success(call_id: str = "call-1", *, suffix: str = "1") -> ToolResult:
    output = JsonObject(
        (
            (
                "candidates",
                (
                    JsonObject(
                        (
                            ("candidate_id", f"source-{suffix}"),
                            ("url", f"https://example.com/{suffix}"),
                            ("title", f"AI 发布 {suffix}"),
                            ("published_at", None),
                            ("summary", f"真实材料 {suffix}"),
                        )
                    ),
                ),
            ),
            ("tool_call_id", call_id),
        )
    )
    return ToolResult("2", output, None, 256, False)


def _pack(*, partial: bool = False, sources: tuple[str, ...] = ("1",)) -> str:
    return json.dumps(
        {
            "contract_version": "evidence-pack/1",
            "topic": "最近 7 天 AI 行业热点",
            "sources": [
                {
                    "source_id": f"source-{suffix}",
                    "tool_call_id": f"call-{suffix}",
                    "url": f"https://example.com/{suffix}",
                    "title": f"AI 发布 {suffix}",
                    "published_at": None,
                    "excerpt": f"真实材料 {suffix}",
                }
                for suffix in sources
            ],
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "项目发布了新版本",
                    "source_ids": [f"source-{sources[0]}"],
                }
            ],
            "hotspots": [
                {
                    "hotspot_id": "hotspot-1",
                    "title": "新版本发布",
                    "summary": "项目发布了新版本",
                    "claim_ids": ["claim-1"],
                    "source_ids": [f"source-{sources[0]}"],
                    "published_at": None,
                    "heat": None,
                }
            ],
            "gaps": ["一个来源调用失败"] if partial else [],
            "partial": partial,
        },
        ensure_ascii=False,
    )


def _reflection(*, complete: bool = True) -> str:
    return json.dumps(
        {
            "complete": complete,
            "problems": [] if complete else ["来源覆盖不足"],
            "repair_instructions": "" if complete else "补充一个独立来源",
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_valid_tool_call_builds_source_claim_hotspot_closure() -> None:
    model = _ModelRuntime(
        (
            ProviderMessage("assistant", None, tool_calls=(_call(),)),
            ProviderMessage("assistant", _pack()),
            ProviderMessage("assistant", _reflection()),
        )
    )
    executor = _Executor({"call-1": _success()})
    assembler = _Assembler()
    loop = ResearchToolLoop(model, assembler, executor)

    pack = await loop.execute(
        _request(), frozenset({"research.discover.v2"}), _budget()
    )

    assert pack.hotspots[0].claim_ids == ("claim-1",)
    assert pack.claims[0].source_ids == ("source-1",)
    assert assembler.keys == [
        "research.plan",
        "research.synthesize",
        "research.reflect",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("calls", "allowed", "code"),
    [
        ((_call(name="unknown.tool"),), frozenset({"research.discover.v2"}), "RESEARCH_TOOL_NOT_ALLOWED"),
        ((_call(url="http://example.com/a"),), frozenset({"research.discover.v2"}), "RESEARCH_TOOL_URL_INVALID"),
        ((_call(), _call("call-2")), frozenset({"research.discover.v2"}), "RESEARCH_TOOL_CALL_DUPLICATE"),
    ],
)
async def test_tool_governance_rejects_unknown_invalid_and_duplicate(
    calls, allowed, code
) -> None:
    model = _ModelRuntime((ProviderMessage("assistant", None, tool_calls=calls),))
    loop = ResearchToolLoop(model, _Assembler(), _Executor({}))

    with pytest.raises(ResearchToolLoopError, match=code):
        await loop.execute(_request(), allowed, _budget())


@pytest.mark.asyncio
async def test_no_successful_source_fails_without_fabricating_pack() -> None:
    failed = ToolResult(
        "2",
        None,
        ToolError("SOURCE_TEMPORARY_FAILURE", "source", True, "失败", "none"),
        0,
        False,
    )
    model = _ModelRuntime(
        (ProviderMessage("assistant", None, tool_calls=(_call(),)),)
    )
    loop = ResearchToolLoop(model, _Assembler(), _Executor({"call-1": failed}))

    with pytest.raises(ResearchToolLoopError, match="RESEARCH_NO_SOURCES"):
        await loop.execute(
            _request(), frozenset({"research.discover.v2"}), _budget()
        )


@pytest.mark.asyncio
async def test_partial_source_failure_is_preserved_as_gap() -> None:
    failed = ToolResult(
        "2",
        None,
        ToolError("SOURCE_RATE_LIMITED", "source", True, "受限", "none"),
        0,
        False,
    )
    calls = (_call("call-1"), _call("call-2", query="AI funding"))
    model = _ModelRuntime(
        (
            ProviderMessage("assistant", None, tool_calls=calls),
            ProviderMessage("assistant", _pack(partial=True)),
            ProviderMessage("assistant", _reflection()),
        )
    )
    loop = ResearchToolLoop(
        model,
        _Assembler(),
        _Executor({"call-1": _success(), "call-2": failed}),
    )

    pack = await loop.execute(
        _request(), frozenset({"research.discover.v2"}), _budget()
    )

    assert pack.partial is True
    assert pack.gaps == ("一个来源调用失败",)


@pytest.mark.asyncio
async def test_one_supplement_round_is_allowed_and_then_stops() -> None:
    second_call = _call("call-2", query="AI funding")
    model = _ModelRuntime(
        (
            ProviderMessage("assistant", None, tool_calls=(_call(),)),
            ProviderMessage("assistant", _pack(partial=True)),
            ProviderMessage("assistant", None, tool_calls=(second_call,)),
            ProviderMessage("assistant", _pack(sources=("1", "2"))),
        )
    )
    executor = _Executor(
        {"call-1": _success(), "call-2": _success("call-2", suffix="2")}
    )
    loop = ResearchToolLoop(model, _Assembler(), executor)

    pack = await loop.execute(
        _request(), frozenset({"research.discover.v2"}), _budget()
    )

    assert len(pack.sources) == 2
    assert [item.tool_call_id for item in executor.calls] == ["call-1", "call-2"]


@pytest.mark.asyncio
async def test_tool_budget_stops_before_network_execution() -> None:
    model = _ModelRuntime(
        (ProviderMessage("assistant", None, tool_calls=(_call(),)),)
    )
    executor = _Executor({"call-1": _success()})
    loop = ResearchToolLoop(model, _Assembler(), executor)

    with pytest.raises(ResearchToolLoopError, match="RESEARCH_BUDGET_EXHAUSTED"):
        await loop.execute(
            _request(),
            frozenset({"research.discover.v2"}),
            _budget(calls=0),
        )
    assert executor.calls == []
