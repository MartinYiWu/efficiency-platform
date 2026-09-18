"""Intent V2 离线标注集的完整性校验与可审计指标。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9]{12,}|api[_-]?key|password|bearer\s+[A-Za-z0-9._-]{12,})",
    re.IGNORECASE,
)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IntentEvaluationCaseV2(_FrozenContract):
    case_id: str = Field(min_length=1, max_length=128)
    semantic_family: str = Field(min_length=1, max_length=128)
    category: Literal["single", "multi", "date", "composite", "attack", "failure"]
    input: str = Field(min_length=1, max_length=20_000)
    timezone: str = Field(min_length=1, max_length=128)
    expected_fields: dict[str, object]
    allowed_defaults: tuple[str, ...] = ()
    expected_decision: Literal["READY", "CLARIFY", "UNSUPPORTED", "FAILED"]
    expected_capabilities: tuple[str, ...] = ()
    source: str = Field(min_length=1, max_length=256)
    annotator: str = Field(min_length=1, max_length=128)

    @field_validator("expected_fields")
    @classmethod
    def validate_expected_fields(cls, value: dict[str, object]) -> dict[str, object]:
        if not value or any(not key.strip() for key in value):
            raise ValueError("EVALUATION_EXPECTED_FIELDS_INVALID")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("EVALUATION_TIMEZONE_INVALID") from exc
        return value


class IntentDatasetFileV2(_FrozenContract):
    split: Literal["development", "regression", "frozen"]
    path: str = Field(min_length=1, max_length=256)
    count: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    tuning_allowed: bool

    @model_validator(mode="after")
    def validate_frozen_policy(self) -> IntentDatasetFileV2:
        if self.split == "frozen" and self.tuning_allowed:
            raise ValueError("FROZEN_DATASET_TUNING_FORBIDDEN")
        return self


class IntentDatasetManifestV2(_FrozenContract):
    schema_version: Literal["intent-evaluation-manifest/2"] = (
        "intent-evaluation-manifest/2"
    )
    dataset_version: str = Field(min_length=1, max_length=128)
    created_at: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=256)
    annotator: str = Field(min_length=1, max_length=128)
    annotation_method: str = Field(min_length=1, max_length=256)
    default_timezone: str = Field(min_length=1, max_length=128)
    total_count: int = Field(ge=1)
    category_counts: dict[str, int]
    files: tuple[IntentDatasetFileV2, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_files(self) -> IntentDatasetManifestV2:
        if {item.split for item in self.files} != {
            "development",
            "regression",
            "frozen",
        }:
            raise ValueError("EVALUATION_SPLITS_INVALID")
        if sum(self.category_counts.values()) != self.total_count:
            raise ValueError("EVALUATION_MANIFEST_TOTAL_INVALID")
        return self


class IntentEvaluationPredictionV2(_FrozenContract):
    case_id: str = Field(min_length=1, max_length=128)
    fields: dict[str, object]
    decision: Literal["READY", "CLARIFY", "UNSUPPORTED", "FAILED"]
    capabilities: tuple[str, ...] = ()


class IntentEvaluationReportV2(_FrozenContract):
    case_correct: int = Field(ge=0)
    case_total: int = Field(ge=0)
    field_correct: int = Field(ge=0)
    field_total: int = Field(ge=0)
    decision_correct: int = Field(ge=0)
    decision_total: int = Field(ge=0)
    capability_correct: int = Field(ge=0)
    capability_total: int = Field(ge=0)
    errors: tuple[str, ...] = Field(default=(), max_length=10_000)


def load_intent_dataset(
    root: Path,
) -> tuple[IntentDatasetManifestV2, tuple[IntentEvaluationCaseV2, ...]]:
    manifest_path = root / "manifest.json"
    manifest = IntentDatasetManifestV2.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    cases: list[IntentEvaluationCaseV2] = []
    families_by_split: dict[str, set[str]] = {}
    case_ids: set[str] = set()
    for declared in manifest.files:
        path = root / declared.path
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != declared.sha256:
            raise ValueError(f"EVALUATION_HASH_MISMATCH:{declared.split}")
        parsed = tuple(
            IntentEvaluationCaseV2.model_validate_json(line)
            for line in payload.decode("utf-8").splitlines()
            if line.strip()
        )
        if len(parsed) != declared.count:
            raise ValueError(f"EVALUATION_COUNT_MISMATCH:{declared.split}")
        split_families = families_by_split.setdefault(declared.split, set())
        for case in parsed:
            if case.case_id in case_ids:
                raise ValueError("EVALUATION_CASE_DUPLICATED")
            if case.semantic_family in split_families:
                raise ValueError("EVALUATION_FAMILY_DUPLICATED_IN_SPLIT")
            serialized = case.model_dump_json()
            if _SECRET_PATTERN.search(serialized):
                raise ValueError("EVALUATION_SECRET_DETECTED")
            case_ids.add(case.case_id)
            split_families.add(case.semantic_family)
        cases.extend(parsed)
    split_names = tuple(families_by_split)
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            if families_by_split[left] & families_by_split[right]:
                raise ValueError("EVALUATION_FAMILY_CROSS_SPLIT")
    if len(cases) != manifest.total_count:
        raise ValueError("EVALUATION_TOTAL_MISMATCH")
    actual_categories: dict[str, int] = {}
    for case in cases:
        actual_categories[case.category] = actual_categories.get(case.category, 0) + 1
    if actual_categories != manifest.category_counts:
        raise ValueError("EVALUATION_CATEGORY_COUNT_MISMATCH")
    return manifest, tuple(cases)


def evaluate_intent_predictions(
    cases: tuple[IntentEvaluationCaseV2, ...],
    predictions: tuple[IntentEvaluationPredictionV2, ...],
) -> IntentEvaluationReportV2:
    by_id = {item.case_id: item for item in predictions}
    if len(by_id) != len(predictions):
        raise ValueError("EVALUATION_PREDICTION_DUPLICATED")
    expected_ids = {item.case_id for item in cases}
    if set(by_id) != expected_ids:
        raise ValueError("EVALUATION_PREDICTION_COVERAGE_MISMATCH")
    case_correct = 0
    field_correct = 0
    field_total = 0
    decision_correct = 0
    capability_correct = 0
    errors: list[str] = []
    for case in cases:
        prediction = by_id[case.case_id]
        case_ok = True
        for field_name, expected in case.expected_fields.items():
            field_total += 1
            if prediction.fields.get(field_name) == expected:
                field_correct += 1
            else:
                case_ok = False
                errors.append(f"{case.case_id}:field:{field_name}")
        unexpected = (
            set(prediction.fields)
            - set(case.expected_fields)
            - set(case.allowed_defaults)
        )
        for field_name in sorted(unexpected):
            case_ok = False
            errors.append(f"{case.case_id}:field_unexpected:{field_name}")
        if prediction.decision == case.expected_decision:
            decision_correct += 1
        else:
            case_ok = False
            errors.append(f"{case.case_id}:decision")
        if prediction.capabilities == case.expected_capabilities:
            capability_correct += 1
        else:
            case_ok = False
            errors.append(f"{case.case_id}:capabilities")
        if case_ok:
            case_correct += 1
    total = len(cases)
    return IntentEvaluationReportV2(
        case_correct=case_correct,
        case_total=total,
        field_correct=field_correct,
        field_total=field_total,
        decision_correct=decision_correct,
        decision_total=total,
        capability_correct=capability_correct,
        capability_total=total,
        errors=tuple(errors),
    )


def canonical_prediction_digest(
    predictions: tuple[IntentEvaluationPredictionV2, ...],
) -> str:
    payload = json.dumps(
        [item.model_dump(mode="json") for item in predictions],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "IntentDatasetFileV2",
    "IntentDatasetManifestV2",
    "IntentEvaluationCaseV2",
    "IntentEvaluationPredictionV2",
    "IntentEvaluationReportV2",
    "canonical_prediction_digest",
    "evaluate_intent_predictions",
    "load_intent_dataset",
]
