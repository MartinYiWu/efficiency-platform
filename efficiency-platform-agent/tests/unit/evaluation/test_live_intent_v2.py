"""Intent V2 真实模型评测执行器的离线契约测试。"""

from __future__ import annotations

import json

import pytest

from efficiency_platform_agent.core.model import (
    ModelCandidate,
    ModelExecutionResult,
    ModelSelection,
    ModelTier,
)
from efficiency_platform_agent.core.run import (
    ProviderError,
    ProviderMessage,
    ProviderResult,
    ProviderUsage,
)
from efficiency_platform_agent.core.runtime import UsageSnapshot
from efficiency_platform_agent.evaluation.intent_v2 import (
    IntentEvaluationCaseV2,
    IntentEvaluationPredictionV2,
)
from efficiency_platform_agent.evaluation.live_intent_v2 import (
    LiveIntentEvaluationError,
    LiveIntentEvaluationRunner,
    normalize_live_prediction,
)


def _case(case_id: str, category: str = "single") -> IntentEvaluationCaseV2:
    return IntentEvaluationCaseV2(
        case_id=case_id,
        semantic_family=f"{case_id}-family",
        category=category,
        input="请收集上周AI行业动态",
        timezone="Asia/Shanghai",
        expected_fields={"topic": "AI行业", "temporal": "last_week"},
        allowed_defaults=("ranking_mode",),
        expected_decision="READY",
        expected_capabilities=("operation.research.insight",),
        source="test",
        annotator="test",
    )


class FakeRuntime:
    def __init__(self, payloads: tuple[str | ProviderError, ...]) -> None:
        self.payloads = list(payloads)
        self.requests = []

    async def complete(self, demand, request, *, remaining_budget):
        self.requests.append((demand, request, remaining_budget))
        payload = self.payloads.pop(0)
        error = payload if isinstance(payload, ProviderError) else None
        message = None if error else ProviderMessage("assistant", payload)
        result = ProviderResult(
            request.contract_version,
            message,
            ProviderUsage(120, 40, 0, 0, 0),
            error,
        )
        candidate = ModelCandidate(
            "deepseek-balanced",
            "deepseek-balanced",
            "fixed-model",
            ModelTier.BALANCED,
            True,
            False,
            64_000,
            True,
            False,
        )
        return ModelExecutionResult(
            result,
            (ModelSelection(candidate, 1, None, "requested_tier"),),
            UsageSnapshot(120, 40, 0, False),
            False,
        )


@pytest.mark.asyncio
async def test_runner_groups_categories_and_records_actual_usage() -> None:
    first = _case("case-single", "single")
    second = _case("case-date", "date")
    runtime = FakeRuntime(
        (
            json.dumps(
                {
                    "predictions": [
                        {
                            "case_id": first.case_id,
                            "fields": {
                                "topic": "AI行业",
                                "temporal": "last_week",
                            },
                            "decision": "READY",
                            "capabilities": ["operation.research.insight"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "predictions": [
                        {
                            "case_id": second.case_id,
                            "fields": {
                                "topic": "AI行业",
                                "temporal": "last_week",
                            },
                            "decision": "READY",
                            "capabilities": ["operation.research.insight"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        )
    )

    result = await LiveIntentEvaluationRunner(runtime).run(
        cases=(first, second),
        run_id="live-run-1",
        dataset_version="dataset-1",
        split="frozen",
        model_id="fixed-model",
        approved_budget_microunits=5_000,
    )

    assert result.artifact["schema_version"] == "intent-evaluation-predictions/2"
    assert result.artifact["usage"] == {
        "model_calls": 2,
        "failed_model_calls": 0,
        "cost_microunits": 0,
    }
    assert result.input_tokens == 240
    assert result.output_tokens == 80
    assert result.external_io is True
    assert [item[0].demand_version for item in runtime.requests] == [
        "intent-v2-evaluation-single/1",
        "intent-v2-evaluation-date/1",
    ]


@pytest.mark.asyncio
async def test_runner_rejects_missing_prediction_coverage() -> None:
    runtime = FakeRuntime((json.dumps({"predictions": []}),))

    with pytest.raises(
        LiveIntentEvaluationError,
        match="LIVE_PREDICTION_COVERAGE_MISMATCH",
    ):
        await LiveIntentEvaluationRunner(runtime).run(
            cases=(_case("case-single"),),
            run_id="live-run-1",
            dataset_version="dataset-1",
            split="frozen",
            model_id="fixed-model",
            approved_budget_microunits=5_000,
        )


@pytest.mark.asyncio
async def test_runner_reports_provider_failure_without_fabricating_predictions() -> None:
    runtime = FakeRuntime(
        (ProviderError("PROVIDER_UNAVAILABLE", "provider", True, "unavailable"),)
    )

    with pytest.raises(
        LiveIntentEvaluationError,
        match="LIVE_PREDICTION_PROVIDER_FAILED",
    ) as captured:
        await LiveIntentEvaluationRunner(runtime).run(
            cases=(_case("case-single"),),
            run_id="live-run-1",
            dataset_version="dataset-1",
            split="frozen",
            model_id="fixed-model",
            approved_budget_microunits=5_000,
        )

    assert captured.value.model_calls == 1
    assert captured.value.failed_model_calls == 1


@pytest.mark.parametrize(
    ("category", "text", "raw_fields", "raw_capabilities", "expected_fields", "expected_capabilities"),
    (
        (
            "multi",
            "沿用新能源主题1，改成昨天并排除融资消息",
            {"topic": "新能源主题1", "temporal": "yesterday", "exclusions": ["融资消息"]},
            (),
            {"topic": "新能源主题1", "temporal": "yesterday", "exclusions": ["融资"]},
            ("operation.research.insight",),
        ),
        (
            "date",
            "按日期语义yesterday收集主题1动态",
            {"topic": "主题1", "temporal": "yesterday"},
            (),
            {"topic": "日期主题1", "temporal": "yesterday"},
            ("operation.research.insight",),
        ),
        (
            "composite",
            "先研究复合主题1，复核证据，再写成公众号",
            {"topic": "复合主题1", "goal_count": 2, "target_platform": "wechat_official_account"},
            ("research", "write"),
            {"topic": "复合主题1", "goal_count": 3, "target_platform": "wechat_official_account"},
            (
                "operation.research.insight",
                "operation.quality.review",
                "operation.channel.content",
            ),
        ),
        (
            "failure",
            "模拟意图Provider故障用例1",
            {"safe_error": "INTENT_PROVIDER_UNAVAILABLE", "tool_calls": 0},
            ("operation.research.insight",),
            {"error": "INTENT_PROVIDER_UNAVAILABLE", "tool_calls": 0},
            (),
        ),
    ),
)
def test_deterministic_normalizer_owns_schema_and_capability_binding(
    category,
    text,
    raw_fields,
    raw_capabilities,
    expected_fields,
    expected_capabilities,
) -> None:
    case = _case(f"case-{category}", category)
    case = case.model_copy(update={"input": text})
    raw = IntentEvaluationPredictionV2(
        case_id=case.case_id,
        fields=raw_fields,
        decision="FAILED" if category == "failure" else "READY",
        capabilities=raw_capabilities,
    )

    normalized = normalize_live_prediction(case, raw)

    assert normalized.fields == expected_fields
    assert normalized.capabilities == expected_capabilities
