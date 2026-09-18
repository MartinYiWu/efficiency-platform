"""I07 Intent V2 离线数据集与指标测试。"""

from __future__ import annotations

from pathlib import Path

from efficiency_platform_agent.evaluation.intent_v2 import (
    IntentEvaluationPredictionV2,
    canonical_prediction_digest,
    evaluate_intent_predictions,
    load_intent_dataset,
)

DATASET_ROOT = Path(__file__).parents[1] / "fixtures" / "intent_v2"


def _oracle_predictions(cases):
    return tuple(
        IntentEvaluationPredictionV2(
            case_id=case.case_id,
            fields=case.expected_fields,
            decision=case.expected_decision,
            capabilities=case.expected_capabilities,
        )
        for case in cases
    )


def test_dataset_has_frozen_counts_hashes_and_no_cross_split_family() -> None:
    manifest, cases = load_intent_dataset(DATASET_ROOT)

    assert manifest.total_count == len(cases) == 240
    assert {item.split: item.count for item in manifest.files} == {
        "development": 120,
        "regression": 60,
        "frozen": 60,
    }
    assert manifest.category_counts == {
        "single": 60,
        "multi": 60,
        "date": 40,
        "composite": 30,
        "attack": 30,
        "failure": 20,
    }
    frozen = next(item for item in manifest.files if item.split == "frozen")
    assert frozen.tuning_allowed is False
    assert all(case.timezone == "Asia/Shanghai" for case in cases)


def test_metrics_report_explicit_numerators_denominators_and_field_errors() -> None:
    _, cases = load_intent_dataset(DATASET_ROOT)
    predictions = _oracle_predictions(cases)
    perfect = evaluate_intent_predictions(cases, predictions)

    assert perfect.case_correct == perfect.case_total == 240
    assert perfect.field_correct == perfect.field_total
    assert perfect.decision_correct == perfect.decision_total == 240
    assert perfect.capability_correct == perfect.capability_total == 240
    assert perfect.errors == ()

    first = predictions[0]
    wrong_fields = dict(first.fields)
    wrong_name = next(iter(wrong_fields))
    wrong_fields[wrong_name] = "wrong"
    wrong = (
        first.model_copy(update={"fields": wrong_fields}),
        *predictions[1:],
    )
    report = evaluate_intent_predictions(cases, wrong)

    assert report.case_correct == 239
    assert report.field_correct == report.field_total - 1
    assert report.errors == (f"{first.case_id}:field:{wrong_name}",)


def test_prediction_digest_is_ordered_and_stable() -> None:
    _, cases = load_intent_dataset(DATASET_ROOT)
    predictions = _oracle_predictions(cases)

    assert canonical_prediction_digest(predictions) == canonical_prediction_digest(
        predictions
    )
    assert canonical_prediction_digest(predictions) != canonical_prediction_digest(
        tuple(reversed(predictions))
    )


def test_only_declared_defaults_may_add_prediction_fields() -> None:
    _, cases = load_intent_dataset(DATASET_ROOT)
    predictions = _oracle_predictions(cases)
    first = predictions[0]
    allowed = dict(first.fields)
    allowed["ranking_mode"] = "importance"
    allowed_predictions = (
        first.model_copy(update={"fields": allowed}),
        *predictions[1:],
    )
    assert evaluate_intent_predictions(cases, allowed_predictions).case_correct == 240

    injected = dict(first.fields)
    injected["tenant_id"] = "attacker"
    injected_predictions = (
        first.model_copy(update={"fields": injected}),
        *predictions[1:],
    )
    report = evaluate_intent_predictions(cases, injected_predictions)
    assert report.case_correct == 239
    assert report.errors == (f"{first.case_id}:field_unexpected:tenant_id",)
