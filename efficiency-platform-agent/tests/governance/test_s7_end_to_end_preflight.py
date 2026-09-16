"""验证 G7 端到端预检只读取本地证据并严格失败关闭。"""

from __future__ import annotations

import json
from pathlib import Path

from efficiency_platform_agent.configuration.integration import (
    IntegrationGate,
    S7IntegrationSettings,
)
from scripts.s7_preflight import preflight_end_to_end


def _settings() -> S7IntegrationSettings:
    """构造只含合成占位值的完整配置。"""
    return S7IntegrationSettings(
        runtime_database_url="postgresql://synthetic",
        vector_database_url="postgresql://synthetic",
        task_broker_url="redis://synthetic",
        run_event_redis_url="redis://synthetic",
        deepseek_base_url="https://example.invalid",
        deepseek_api_key="synthetic",
        deepseek_fast_model="fast",
        deepseek_balanced_model="balanced",
        deepseek_strong_model="strong",
        cos_secret_id="synthetic",
        cos_secret_key="synthetic",
        cos_region="synthetic",
        cos_bucket="synthetic",
        cos_base_url="https://example.invalid",
    )


def _write_authorizations(path: Path, now_epoch_ms: int) -> None:
    """写入 G7 和三个子 Gate 的合成有效授权。"""
    records = []
    for gate, action in (
        ("end_to_end", "network_probe"),
        ("deepseek_chat", "charged_acceptance"),
        ("postgres_pgvector", "write_acceptance"),
        ("cos_artifact", "write_acceptance"),
    ):
        records.append(
            {
                "approval_id": f"approval-{gate}",
                "run_stamp": "s7-e2e-synthetic",
                "gate": gate,
                "action": action,
                "approved_by": "reviewer",
                "executor_id": "executor",
                "target_digest": "target",
                "input_digest": "input",
                "model_ids": [],
                "resource_ids": [],
                "approved_at_epoch_ms": now_epoch_ms - 1_000,
                "expires_at_epoch_ms": now_epoch_ms + 60_000,
                "max_network_calls": 20,
                "max_model_calls": 12,
                "max_search_calls": 4,
                "max_cost_microunits": 0 if action == "network_probe" else 1_000_000,
                "max_database_rows_read": 100,
                "max_database_rows_written": 0 if action == "network_probe" else 100,
                "max_redis_records": 0 if action == "network_probe" else 20,
                "max_cos_objects": 0 if action == "network_probe" else 3,
                "max_bytes": 1_048_576,
                "cleanup_owner": "executor",
                "cleanup_deadline_epoch_ms": now_epoch_ms + 120_000,
                "cleanup_procedure_id": "cleanup-synthetic",
            }
        )
    path.write_text(
        json.dumps({"version": "s7-authorization/1", "authorizations": records}),
        encoding="utf-8",
    )


def _write_evidence(root: Path) -> None:
    """写入三个已选子 Gate 的成功脱敏证据。"""
    root.mkdir()
    for name in (
        "g1-deepseek-chat-acceptance.json",
        "g3-postgres-pgvector-acceptance.json",
        "g5-cos-artifact-acceptance.json",
    ):
        (root / name).write_text(
            json.dumps({"status": "SUCCEEDED", "cleanup_ok": True}),
            encoding="utf-8",
        )


def _write_manifest(path: Path) -> None:
    """写入具备清理责任的合成清单。"""
    path.write_text(
        json.dumps(
            {
                "version": "s7-cleanup-manifest/1",
                "run_stamp": "s7-e2e-synthetic",
                "cleanup_owner": "executor",
                "cleanup_procedure_id": "cleanup-synthetic",
                "local_paths": [],
                "external_prefixes": ["s7/s7-e2e-synthetic/"],
                "external": {
                    "postgres_schema": "s7_acceptance_abcdef12",
                    "redis_prefixes": [],
                    "cos_prefixes": ["s7/s7-e2e-synthetic/"],
                },
            }
        ),
        encoding="utf-8",
    )


def test_end_to_end_preflight_fails_closed_when_configuration_is_missing(
    tmp_path: Path,
) -> None:
    """缺少配置时必须只返回本地阻断结论。"""
    result = preflight_end_to_end(
        settings=S7IntegrationSettings(),
        selected_sub_gates=(IntegrationGate.DEEPSEEK_CHAT,),
        approval_file=tmp_path / "missing.json",
        evidence_root=tmp_path / "evidence",
        manifest_path=tmp_path / "manifest.json",
        now_epoch_ms=10_000,
    )

    assert result["status"] == "BLOCKED"
    assert result["external_io"] is False
    assert "configuration_missing" in result["reason_codes"]
    assert result["selected_real_gates"] == []


def test_end_to_end_preflight_is_ready_with_fresh_local_evidence(
    tmp_path: Path,
) -> None:
    """配置、授权、证据和清理清单齐全时可以进入真实执行阶段。"""
    now = 10_000
    approval_file = tmp_path / "authorization.json"
    evidence_root = tmp_path / "evidence"
    manifest_path = tmp_path / "manifest.json"
    _write_authorizations(approval_file, now)
    _write_evidence(evidence_root)
    _write_manifest(manifest_path)

    result = preflight_end_to_end(
        settings=_settings(),
        selected_sub_gates=(
            IntegrationGate.DEEPSEEK_CHAT,
            IntegrationGate.POSTGRES_PGVECTOR,
            IntegrationGate.COS_ARTIFACT,
        ),
        approval_file=approval_file,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        now_epoch_ms=now,
    )

    assert result["status"] == "READY"
    assert result["external_io"] is False
    assert result["reason_codes"] == []
    assert result["selected_real_gates"] == []


def test_end_to_end_preflight_rejects_failed_sub_gate_evidence(tmp_path: Path) -> None:
    """任一子 Gate 失败都不得进入 G7 真实执行。"""
    now = 10_000
    approval_file = tmp_path / "authorization.json"
    evidence_root = tmp_path / "evidence"
    manifest_path = tmp_path / "manifest.json"
    _write_authorizations(approval_file, now)
    _write_evidence(evidence_root)
    _write_manifest(manifest_path)
    (evidence_root / "g3-postgres-pgvector-acceptance.json").write_text(
        json.dumps({"status": "FAILED", "cleanup_ok": True}), encoding="utf-8"
    )

    result = preflight_end_to_end(
        settings=_settings(),
        selected_sub_gates=(IntegrationGate.POSTGRES_PGVECTOR,),
        approval_file=approval_file,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        now_epoch_ms=now,
    )

    assert result["status"] == "BLOCKED"
    assert "sub_gate_not_ready" in result["reason_codes"]


def test_end_to_end_preflight_rejects_missing_cleanup_responsibility(
    tmp_path: Path,
) -> None:
    """清理责任不完整时不得进入 G7。"""
    now = 10_000
    approval_file = tmp_path / "authorization.json"
    evidence_root = tmp_path / "evidence"
    manifest_path = tmp_path / "manifest.json"
    _write_authorizations(approval_file, now)
    _write_evidence(evidence_root)
    manifest_path.write_text(
        json.dumps({"version": "s7-cleanup-manifest/1", "local_paths": []}),
        encoding="utf-8",
    )

    result = preflight_end_to_end(
        settings=_settings(),
        selected_sub_gates=(IntegrationGate.DEEPSEEK_CHAT,),
        approval_file=approval_file,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        now_epoch_ms=now,
    )

    assert result["status"] == "BLOCKED"
    assert "cleanup_manifest_invalid" in result["reason_codes"]


def test_end_to_end_preflight_rejects_malformed_authorization_without_io(
    tmp_path: Path,
) -> None:
    """授权记录结构错误时必须失败关闭而不是抛出异常。"""
    approval_file = tmp_path / "authorization.json"
    approval_file.write_text(
        json.dumps({"version": "s7-authorization/1", "authorizations": {}}),
        encoding="utf-8",
    )
    result = preflight_end_to_end(
        settings=S7IntegrationSettings(),
        selected_sub_gates=(IntegrationGate.DEEPSEEK_CHAT,),
        approval_file=approval_file,
        evidence_root=tmp_path / "evidence",
        manifest_path=tmp_path / "manifest.json",
        now_epoch_ms=10_000,
    )
    assert result["status"] == "BLOCKED"
    assert "authorization_invalid" in result["reason_codes"]
    assert result["external_io"] is False


__all__ = []
