"""上传文件复盘的离线接线验收。"""

import json

import pytest

from scripts.s7_cleanup import (
    cleanup_external_targets,
    cleanup_manifest,
    validate_external_cleanup_manifest,
)
from scripts.s7_verify import run_offline_scenario, verify


def test_uploaded_file_review_keeps_document_references() -> None:
    result = run_offline_scenario("uploaded_file_review")
    assert result["status"] == "SUCCEEDED"
    assert result["document_references"]
    assert result["external_io"] is False


def test_offline_manifest_cleanup_is_precise(tmp_path) -> None:
    result = verify(gate="offline", offline=True, evidence_root=tmp_path)
    manifest = tmp_path / "latest-manifest.json"
    assert result["manifest"] == str(manifest)
    cleaned = cleanup_manifest(manifest)
    assert cleaned["status"] == "CLEANED"
    assert not (tmp_path / "industry_digest.json").exists()
    assert manifest.exists()


def test_cleanup_rejects_malformed_local_path_list(tmp_path) -> None:
    manifest = tmp_path / "malformed.json"
    manifest.write_text('{"local_paths":"not-a-list"}', encoding="utf-8")

    with pytest.raises(ValueError, match="清理清单格式无效"):
        cleanup_manifest(manifest)


def test_cleanup_rejects_invalid_json_manifest(tmp_path) -> None:
    manifest = tmp_path / "invalid-json.json"
    manifest.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match="清理清单格式无效"):
        cleanup_manifest(manifest)


def test_cleanup_rejects_directory_target(tmp_path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    manifest = tmp_path / "directory.json"
    manifest.write_text(json.dumps({"local_paths": [str(directory)]}), encoding="utf-8")

    with pytest.raises(ValueError, match="清理目标必须是文件"):
        cleanup_manifest(manifest)


def test_cleanup_accepts_only_exact_external_targets() -> None:
    validated = validate_external_cleanup_manifest(
        {
            "external": {
                "postgres_schema": "s7_acceptance_abcdef12",
                "redis_prefixes": ["s7:run-1:"],
                "cos_prefixes": ["s7/run-1/"],
            }
        }
    )
    assert validated["postgres_schema"] == "s7_acceptance_abcdef12"
    assert validated["redis_prefixes"] == ["s7:run-1:"]
    assert validated["cos_prefixes"] == ["s7/run-1/"]


@pytest.mark.parametrize(
    "external",
    [
        {"postgres_schema": "public"},
        {"redis_prefixes": ["*"]},
        {"redis_prefixes": ["s7:"]},
        {"cos_prefixes": ["/"]},
        {"flushall": True},
    ],
)
def test_cleanup_rejects_broad_external_targets(external) -> None:
    with pytest.raises(ValueError):
        validate_external_cleanup_manifest({"external": external})


def test_external_cleanup_requires_injected_cleaners_without_network(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "s7-cleanup-manifest/1",
                "run_stamp": "run-1",
                "cleanup_owner": "owner",
                "cleanup_procedure_id": "procedure-1",
                "local_paths": [],
                "external_prefixes": [],
                "external": {
                    "postgres_schema": "s7_acceptance_abcdef12",
                    "redis_prefixes": ["s7:run-1:"],
                    "cos_prefixes": ["s7/run-1/"],
                },
            }
        ),
        encoding="utf-8",
    )

    result = cleanup_external_targets(manifest)

    assert result == {
        "status": "NOT_EXECUTED",
        "reason": "external_cleaner_missing",
        "external_cleanup_executed": False,
    }


def test_external_cleanup_calls_only_validated_targets(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "s7-cleanup-manifest/1",
                "run_stamp": "run-1",
                "cleanup_owner": "owner",
                "cleanup_procedure_id": "procedure-1",
                "local_paths": [],
                "external_prefixes": [],
                "external": {
                    "postgres_schema": "s7_acceptance_abcdef12",
                    "redis_prefixes": ["s7:run-1:"],
                    "cos_prefixes": ["s7/run-1/"],
                },
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[str, str]] = []

    def postgres(target: str):
        calls.append(("postgres", target))
        return {"cleanup_ok": True}

    def redis(target: str):
        calls.append(("redis", target))
        return {"cleanup_ok": True}

    def cos(target: str):
        calls.append(("cos", target))
        return {"cleanup_ok": True}

    result = cleanup_external_targets(
        manifest,
        postgres_cleaner=postgres,
        redis_cleaner=redis,
        cos_cleaner=cos,
    )

    assert result["status"] == "CLEANED"
    assert result["cleanup_ok"] is True
    assert calls == [
        ("postgres", "s7_acceptance_abcdef12"),
        ("redis", "s7:run-1:"),
        ("cos", "s7/run-1/"),
    ]


def test_external_cleanup_validates_before_invoking_any_cleaner(tmp_path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "s7-cleanup-manifest/1",
                "run_stamp": "run-1",
                "cleanup_owner": "owner",
                "cleanup_procedure_id": "procedure-1",
                "local_paths": [],
                "external_prefixes": [],
                "external": {"redis_prefixes": ["*"]},
            }
        ),
        encoding="utf-8",
    )
    called = False

    def cleaner(_target: str):
        nonlocal called
        called = True
        return {}

    result = cleanup_external_targets(manifest, redis_cleaner=cleaner)

    assert result["status"] == "FAILED"
    assert result["external_cleanup_executed"] is False
    assert called is False
