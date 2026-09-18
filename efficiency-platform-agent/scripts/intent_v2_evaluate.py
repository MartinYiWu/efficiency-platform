"""Intent V2 冻结集评测汇总器。

脚本只评分外部生成并固定的预测工件。没有预测时只校验数据集，不使用标签
生成“预测”；至少三次独立运行后才给出质量门禁结论。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
for search_path in (PROJECT_ROOT, SOURCE_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from efficiency_platform_agent.evaluation.intent_v2 import (  # type: ignore[import-untyped]
    IntentEvaluationCaseV2,
    IntentEvaluationPredictionV2,
    canonical_prediction_digest,
    evaluate_intent_predictions,
    load_intent_dataset,
)
from efficiency_platform_agent.evaluation.live_intent_v2 import (  # type: ignore[import-untyped]
    LiveIntentEvaluationError,
    LiveIntentEvaluationRunner,
)
from scripts.research_v2_acceptance import validate_live_authorization

type Split = Literal["development", "regression", "frozen"]


async def execute_live_evaluation(
    *,
    dataset_root: Path,
    split: Split,
    env_file: Path,
    artifact_dir: Path,
    approved_budget_microunits: int,
    run_count: int = 3,
) -> dict[str, Any]:
    """通过项目统一 ModelRuntime 执行独立真实评测并立即回放评分。"""

    if run_count < 3:
        raise ValueError("THREE_INDEPENDENT_RUNS_REQUIRED")
    from openai import AsyncOpenAI

    from efficiency_platform_agent.capabilities.model.runtime import ModelRuntime
    from efficiency_platform_agent.configuration.integration import (
        S7IntegrationSettings,
    )
    from efficiency_platform_agent.core.model import ModelCandidate, ModelTier
    from efficiency_platform_agent.providers.llm.deepseek import DeepSeekModelProvider
    from efficiency_platform_agent.providers.llm.registry import ModelProviderRegistry
    from efficiency_platform_agent.routing.model_router import ModelPolicyRouter

    settings = S7IntegrationSettings.from_env_file(env_file)

    def required(name: str) -> str:
        value = getattr(settings, name)
        if value is None or not value.get_secret_value().strip():
            raise ValueError(f"LIVE_MODEL_CONFIGURATION_MISSING:{name}")
        return value.get_secret_value()

    base_url = required("deepseek_base_url")
    api_key = required("deepseek_api_key")
    model_id = required("deepseek_balanced_model")
    dataset_version, cases = _split_cases(dataset_root, split)
    per_run_budget = max(1, approved_budget_microunits // run_count)
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    # DeepSeek 走 OpenAI-compatible chat.completions；显式隐藏 SDK 的 Responses
    # 入口，避免适配器误选厂商未提供的 /responses 路由。
    provider_client = SimpleNamespace(chat=client.chat, close=client.close)
    provider = DeepSeekModelProvider(provider_client, model_id, timeout_ms=120_000)
    registry = ModelProviderRegistry()
    provider_id = "deepseek_live_intent_evaluation"
    registry.register(provider_id, provider)
    candidate = ModelCandidate(
        "deepseek-live-intent-evaluation",
        provider_id,
        model_id,
        ModelTier.BALANCED,
        True,
        False,
        64_000,
        True,
        False,
    )
    runner = LiveIntentEvaluationRunner(
        ModelRuntime(ModelPolicyRouter((candidate,)), registry)
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    executions: list[dict[str, object]] = []
    try:
        for index in range(run_count):
            run_id = f"live-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:12]}"
            completed = await runner.run(
                cases=cases,
                run_id=run_id,
                dataset_version=dataset_version,
                split=split,
                model_id=model_id,
                approved_budget_microunits=per_run_budget,
            )
            path = artifact_dir / f"{run_id}.json"
            path.write_text(
                json.dumps(completed.artifact, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            paths.append(path)
            usage = cast(dict[str, int], completed.artifact["usage"])
            executions.append(
                {
                    "run_id": run_id,
                    "model_calls": usage["model_calls"],
                    "failed_model_calls": usage["failed_model_calls"],
                    "input_tokens": completed.input_tokens,
                    "output_tokens": completed.output_tokens,
                    "cost_microunits": usage["cost_microunits"],
                    "latency_ms": completed.latency_ms,
                    "external_io": completed.external_io,
                }
            )
    finally:
        await provider.close()
    report = evaluate_replay(
        dataset_root=dataset_root,
        split=split,
        prediction_files=tuple(paths),
    )
    return {
        **report,
        "execution_mode": "live",
        "external_io": True,
        "executions": executions,
        "prediction_artifacts": [str(path) for path in paths],
    }


def _split_cases(
    dataset_root: Path, split: Split
) -> tuple[str, tuple[IntentEvaluationCaseV2, ...]]:
    manifest, cases = load_intent_dataset(dataset_root)
    declared = next(item for item in manifest.files if item.split == split)
    selected_ids = {
        json.loads(line)["case_id"]
        for line in (dataset_root / declared.path)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    selected = tuple(case for case in cases if case.case_id in selected_ids)
    return manifest.dataset_version, selected


def _load_prediction_run(
    path: Path,
    *,
    dataset_version: str,
    split: Split,
) -> tuple[dict[str, object], tuple[IntentEvaluationPredictionV2, ...]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("PREDICTION_ARTIFACT_INVALID") from exc
    required = {
        "schema_version",
        "run_id",
        "dataset_version",
        "split",
        "model_id",
        "prompt_versions",
        "usage",
        "predictions",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("PREDICTION_ARTIFACT_INVALID")
    usage = payload["usage"]
    if not (
        payload["schema_version"] == "intent-evaluation-predictions/2"
        and payload["dataset_version"] == dataset_version
        and payload["split"] == split
        and isinstance(payload["run_id"], str)
        and payload["run_id"].strip()
        and isinstance(payload["model_id"], str)
        and payload["model_id"].strip()
        and isinstance(payload["prompt_versions"], list)
        and payload["prompt_versions"]
        and all(isinstance(item, str) and item for item in payload["prompt_versions"])
        and isinstance(usage, dict)
        and set(usage) == {"model_calls", "failed_model_calls", "cost_microunits"}
        and isinstance(usage["model_calls"], int)
        and not isinstance(usage["model_calls"], bool)
        and usage["model_calls"] > 0
        and isinstance(usage["failed_model_calls"], int)
        and not isinstance(usage["failed_model_calls"], bool)
        and 0 <= usage["failed_model_calls"] <= usage["model_calls"]
        and isinstance(usage["cost_microunits"], int)
        and not isinstance(usage["cost_microunits"], bool)
        and usage["cost_microunits"] >= 0
        and isinstance(payload["predictions"], list)
    ):
        raise ValueError("PREDICTION_ARTIFACT_INVALID")
    predictions = tuple(
        IntentEvaluationPredictionV2.model_validate(item)
        for item in payload["predictions"]
    )
    metadata: dict[str, object] = {
        "run_id": payload["run_id"],
        "model_id": payload["model_id"],
        "prompt_versions": payload["prompt_versions"],
        "usage": usage,
    }
    return metadata, predictions


def _ratio(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


def evaluate_replay(
    *,
    dataset_root: Path,
    split: Split,
    prediction_files: tuple[Path, ...],
) -> dict[str, Any]:
    dataset_version, cases = _split_cases(dataset_root, split)
    base: dict[str, Any] = {
        "schema_version": "intent-v2-evaluation-report/2",
        "dataset_version": dataset_version,
        "split": split,
        "dataset_count": len(cases),
        "evaluation_run_count": len(prediction_files),
    }
    if not prediction_files:
        return {
            **base,
            "status": "NOT_EXECUTED",
            "reason_codes": ["PREDICTIONS_REQUIRED"],
        }
    if len(prediction_files) < 3:
        return {
            **base,
            "status": "NOT_EXECUTED",
            "reason_codes": ["THREE_INDEPENDENT_RUNS_REQUIRED"],
        }

    runs: list[dict[str, object]] = []
    run_ids: set[str] = set()
    fixed_model_id: str | None = None
    fixed_prompt_versions: tuple[str, ...] | None = None
    total_cost = 0
    total_calls = 0
    total_failed_calls = 0
    for path in prediction_files:
        metadata, predictions = _load_prediction_run(
            path, dataset_version=dataset_version, split=split
        )
        run_id = str(metadata["run_id"])
        if run_id in run_ids:
            raise ValueError("EVALUATION_RUN_NOT_INDEPENDENT")
        run_ids.add(run_id)
        model_id = str(metadata["model_id"])
        prompt_versions = tuple(cast(list[str], metadata["prompt_versions"]))
        if fixed_model_id is None:
            fixed_model_id = model_id
            fixed_prompt_versions = prompt_versions
        elif model_id != fixed_model_id or prompt_versions != fixed_prompt_versions:
            raise ValueError("EVALUATION_VERSION_DRIFT")
        report = evaluate_intent_predictions(cases, predictions)
        predictions_by_id = {item.case_id: item for item in predictions}
        predicted_ready = sum(item.decision == "READY" for item in predictions)
        true_ready = sum(
            predictions_by_id[case.case_id].decision == "READY"
            and case.expected_decision == "READY"
            for case in cases
        )
        expected_ready = sum(case.expected_decision == "READY" for case in cases)
        complete_ready = sum(
            case.expected_decision == "READY"
            and predictions_by_id[case.case_id].decision == "READY"
            and all(
                predictions_by_id[case.case_id].fields.get(field_name) == expected
                for field_name, expected in case.expected_fields.items()
            )
            and not (
                set(predictions_by_id[case.case_id].fields)
                - set(case.expected_fields)
                - set(case.allowed_defaults)
            )
            and predictions_by_id[case.case_id].capabilities
            == case.expected_capabilities
            for case in cases
        )
        usage = metadata["usage"]
        assert isinstance(usage, dict)
        total_cost += int(usage["cost_microunits"])
        total_calls += int(usage["model_calls"])
        total_failed_calls += int(usage["failed_model_calls"])
        metrics = {
            "key_field_accuracy": _ratio(report.field_correct, report.field_total),
            "ready_precision": _ratio(
                true_ready,
                predicted_ready,
                empty=0.0 if expected_ready else 1.0,
            ),
            "complete_request_coverage": _ratio(complete_ready, expected_ready),
            "case_accuracy": _ratio(report.case_correct, report.case_total),
            "field_numerator": report.field_correct,
            "field_denominator": report.field_total,
            "ready_true_positive": true_ready,
            "ready_predicted": predicted_ready,
            "ready_expected": expected_ready,
            "complete_ready": complete_ready,
            "case_numerator": report.case_correct,
            "case_denominator": report.case_total,
        }
        passed = (
            metrics["key_field_accuracy"] >= 0.95
            and metrics["ready_precision"] >= 0.98
            and metrics["complete_request_coverage"] >= 0.90
        )
        runs.append(
            {
                **metadata,
                "prediction_digest": canonical_prediction_digest(predictions),
                "passed": passed,
                "metrics": metrics,
                "errors": list(report.errors),
            }
        )
    return {
        **base,
        "status": "PASS" if all(bool(run["passed"]) for run in runs) else "FAIL",
        "thresholds": {
            "key_field_accuracy": 0.95,
            "ready_precision": 0.98,
            "complete_request_coverage": 0.90,
        },
        "usage": {
            "model_calls": total_calls,
            "failed_model_calls": total_failed_calls,
            "cost_microunits": total_cost,
        },
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument(
        "--split", choices=("development", "regression", "frozen"), default="frozen"
    )
    parser.add_argument(
        "--dataset-root", type=Path, default=PROJECT_ROOT / "tests/fixtures/intent_v2"
    )
    parser.add_argument("--predictions", action="append", type=Path, default=[])
    parser.add_argument("--approved-budget-microunits", type=int, default=0)
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--tenant-id")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=PROJECT_ROOT / ".local-acceptance/intent-v2",
    )
    parser.add_argument("--run-count", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "live":
        if args.authorization_file is None:
            reason = "LIVE_AUTHORIZATION_REQUIRED"
        else:
            try:
                validate_live_authorization(
                    args.authorization_file,
                    requested_budget_microunits=args.approved_budget_microunits,
                    requested_actions=("model_evaluation",),
                    requested_case_ids=(),
                    requested_tenant_id=args.tenant_id or "",
                )
            except (TypeError, ValueError) as exc:
                reason = str(exc)
            else:
                reason = ""
        if reason:
            result: dict[str, Any] = {
                "schema_version": "intent-v2-evaluation-report/2",
                "status": "BLOCKED",
                "external_io": False,
                "reason_codes": [reason],
            }
        else:
            try:
                result = asyncio.run(
                    execute_live_evaluation(
                        dataset_root=args.dataset_root,
                        split=cast(Split, args.split),
                        env_file=args.env_file,
                        artifact_dir=args.artifact_dir,
                        approved_budget_microunits=args.approved_budget_microunits,
                        run_count=args.run_count,
                    )
                )
            except (LiveIntentEvaluationError, OSError, ValueError) as exc:
                result = {
                    "schema_version": "intent-v2-evaluation-report/2",
                    "status": "BLOCKED",
                    "external_io": isinstance(exc, LiveIntentEvaluationError)
                    and exc.model_calls > 0,
                    "reason_codes": [str(exc)],
                }
    else:
        result = evaluate_replay(
            dataset_root=args.dataset_root,
            split=args.split,
            prediction_files=tuple(args.predictions),
        )
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if result["status"] in {"PASS", "NOT_EXECUTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["evaluate_replay", "main"]
