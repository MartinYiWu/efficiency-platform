"""S7 本地安全预检，只输出版本和配置键状态，不构造客户端。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from efficiency_platform_agent.configuration.integration import (  # type: ignore[import-untyped]
    GateAction,
    GateAuthorization,
    IntegrationGate,
    S7IntegrationSettings,
)

_GATE_EVIDENCE = {
    IntegrationGate.DEEPSEEK_CHAT: "g1-deepseek-chat-acceptance.json",
    IntegrationGate.DEEPSEEK_WEB_SEARCH: "g2-deepseek-web-search-acceptance.json",
    IntegrationGate.POSTGRES_PGVECTOR: "g3-postgres-pgvector-acceptance.json",
    IntegrationGate.REDIS_TASKIQ: "g4-redis-taskiq-acceptance.json",
    IntegrationGate.COS_ARTIFACT: "g5-cos-artifact-acceptance.json",
    IntegrationGate.DOCUMENT_PIPELINE: "g6-document-pipeline-acceptance.json",
}

_REQUIRED_ACTION = {
    IntegrationGate.DEEPSEEK_CHAT: GateAction.CHARGED_ACCEPTANCE,
    IntegrationGate.DEEPSEEK_WEB_SEARCH: GateAction.CHARGED_ACCEPTANCE,
    IntegrationGate.POSTGRES_PGVECTOR: GateAction.WRITE_ACCEPTANCE,
    IntegrationGate.REDIS_TASKIQ: GateAction.WRITE_ACCEPTANCE,
    IntegrationGate.COS_ARTIFACT: GateAction.WRITE_ACCEPTANCE,
    IntegrationGate.DOCUMENT_PIPELINE: GateAction.READ_ACCEPTANCE,
}

_CLEANUP_REQUIRED = {
    IntegrationGate.POSTGRES_PGVECTOR,
    IntegrationGate.REDIS_TASKIQ,
    IntegrationGate.COS_ARTIFACT,
    IntegrationGate.DOCUMENT_PIPELINE,
}


def _pypdf_security_status() -> str:
    """根据已安装主版本输出本地安全状态，不访问网络。"""

    try:
        installed_version = version("pypdf")
        major_version = int(installed_version.split(".", 1)[0])
    except (PackageNotFoundError, ValueError):
        return "unknown"
    return "blocked" if major_version < 6 else "clear"


def _configuration_missing(
    settings: S7IntegrationSettings,
    selected_sub_gates: tuple[IntegrationGate, ...],
) -> tuple[str, ...]:
    """只检查本次选择的子 Gate 配置，不扩大到未选能力。"""
    missing: set[str] = set()
    for gate in selected_sub_gates:
        selected = settings.model_copy(update={"gates": {gate.value: True}})
        missing.update(selected.for_gate(gate))
    return tuple(sorted(missing))


def _evidence_ready(
    evidence_root: Path,
    gate: IntegrationGate,
) -> bool:
    """只读取脱敏证据状态，不读取响应正文或外部资源。"""
    name = _GATE_EVIDENCE.get(gate)
    if name is None:
        return False
    target = evidence_root / name
    if not target.is_file():
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict) or data.get("status") != "SUCCEEDED":
        return False
    return gate not in _CLEANUP_REQUIRED or data.get("cleanup_ok") is True


def _cleanup_manifest_ready(
    manifest_path: Path, selected_sub_gates: tuple[IntegrationGate, ...]
) -> bool:
    """校验清理清单具备版本、运行标识和明确责任。"""
    if not manifest_path.is_file():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("version") != "s7-cleanup-manifest/1":
        return False
    for key in ("run_stamp", "cleanup_owner", "cleanup_procedure_id"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    for key in ("local_paths", "external_prefixes"):
        values = data.get(key)
        if not isinstance(values, list) or any(
            not isinstance(item, str) for item in values
        ):
            return False
    from scripts.s7_cleanup import validate_external_cleanup_manifest

    try:
        external = validate_external_cleanup_manifest(data)
    except (TypeError, ValueError):
        return False
    if (
        IntegrationGate.POSTGRES_PGVECTOR in selected_sub_gates
        and external["postgres_schema"] is None
    ):
        return False
    if (
        IntegrationGate.REDIS_TASKIQ in selected_sub_gates
        and not external["redis_prefixes"]
    ):
        return False
    return not (
        IntegrationGate.COS_ARTIFACT in selected_sub_gates
        and not external["cos_prefixes"]
    )


def _load_authorizations(path: Path) -> tuple[GateAuthorization, ...]:
    """读取并校验本地授权记录，不输出任何敏感字段。"""
    if not path.is_file():
        raise ValueError("authorization_file_missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("authorization_file_invalid") from error
    if not isinstance(data, dict) or data.get("version") != "s7-authorization/1":
        raise ValueError("authorization_file_invalid")
    records = data.get("authorizations")
    if not isinstance(records, list):
        raise TypeError("authorization_file_invalid")
    try:
        return tuple(GateAuthorization.model_validate(item) for item in records)
    except (TypeError, ValueError) as error:
        raise ValueError("authorization_file_invalid") from error


def preflight_end_to_end(
    *,
    settings: S7IntegrationSettings,
    selected_sub_gates: tuple[IntegrationGate, ...],
    approval_file: Path,
    evidence_root: Path,
    manifest_path: Path,
    now_epoch_ms: int | None = None,
) -> dict[str, Any]:
    """零网络核对 G7 子 Gate、授权、证据和清理清单。"""
    reasons: list[str] = []
    invalid_selection = (
        not selected_sub_gates
        or len(set(selected_sub_gates)) != len(selected_sub_gates)
        or IntegrationGate.END_TO_END in selected_sub_gates
    )
    if invalid_selection:
        reasons.append("sub_gate_selection_invalid")
    missing = _configuration_missing(settings, selected_sub_gates)
    if missing:
        reasons.append("configuration_missing")

    now = now_epoch_ms if now_epoch_ms is not None else int(time.time() * 1000)
    try:
        authorizations = _load_authorizations(approval_file)
    except (TypeError, ValueError):
        authorizations = ()
        reasons.append("authorization_invalid")
    else:
        expected = ((IntegrationGate.END_TO_END, GateAction.NETWORK_PROBE),) + tuple(
            (gate, _REQUIRED_ACTION[gate])
            for gate in selected_sub_gates
            if gate in _REQUIRED_ACTION
        )
        for gate, action in expected:
            if not any(
                item.gate is gate
                and item.action is action
                and item.approved_at_epoch_ms <= now < item.expires_at_epoch_ms
                for item in authorizations
            ):
                reasons.append("authorization_missing_or_expired")
                break

    evidence_status = {
        gate.value: _evidence_ready(evidence_root, gate) for gate in selected_sub_gates
    }
    if evidence_status and not all(evidence_status.values()):
        reasons.append("sub_gate_not_ready")
    if not _cleanup_manifest_ready(manifest_path, selected_sub_gates):
        reasons.append("cleanup_manifest_invalid")

    return {
        "status": "READY" if not reasons else "BLOCKED",
        "external_io": False,
        "selected_real_gates": [],
        "selected_sub_gates": [gate.value for gate in selected_sub_gates],
        "missing_configuration": list(missing),
        "sub_gate_evidence": evidence_status,
        "reason_codes": list(dict.fromkeys(reasons)),
        "limits": {
            "max_model_calls": 12,
            "max_search_calls": 4,
            "max_database_rows_written": 100,
            "max_redis_records": 20,
            "max_cos_objects": 3,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", default="all")
    parser.add_argument("--selected-sub-gate", action="append", default=[])
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    env_path = PROJECT_ROOT / ".env"
    settings = (
        S7IntegrationSettings.from_env_file(env_path)
        if env_path.is_file()
        else S7IntegrationSettings()
    )
    print(f"python={sys.version_info.major}.{sys.version_info.minor}")
    print(f"pypdf_security={_pypdf_security_status()}")
    gates = (
        list(IntegrationGate) if args.gate == "all" else [IntegrationGate(args.gate)]
    )
    for gate in gates:
        print(
            f"{gate.value}=enabled:{settings.gates.get(gate.value, False)} missing:{','.join(settings.for_gate(gate))}"
        )
    if args.gate == IntegrationGate.END_TO_END.value:
        try:
            selected_sub_gates = tuple(
                IntegrationGate(value) for value in args.selected_sub_gate
            )
        except ValueError:
            result = {
                "status": "BLOCKED",
                "external_io": False,
                "selected_real_gates": [],
                "selected_sub_gates": list(args.selected_sub_gate),
                "missing_configuration": [],
                "sub_gate_evidence": {},
                "reason_codes": ["sub_gate_selection_invalid"],
                "limits": {
                    "max_model_calls": 12,
                    "max_search_calls": 4,
                    "max_database_rows_written": 100,
                    "max_redis_records": 20,
                    "max_cos_objects": 3,
                },
            }
        else:
            result = preflight_end_to_end(
                settings=settings,
                selected_sub_gates=selected_sub_gates,
                approval_file=args.approval_file
                or PROJECT_ROOT
                / "docs"
                / "superpowers"
                / "sdd"
                / "operation-acceptance-s7"
                / "授权记录.json",
                evidence_root=args.evidence_root
                or PROJECT_ROOT
                / "docs"
                / "superpowers"
                / "sdd"
                / "operation-acceptance-s7"
                / "evidence",
                manifest_path=args.manifest
                or PROJECT_ROOT
                / "docs"
                / "superpowers"
                / "sdd"
                / "operation-acceptance-s7"
                / "evidence"
                / "latest-manifest.json",
            )
        print(f"end_to_end_preflight={json.dumps(result, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "preflight_end_to_end"]
