"""X04 研究来源准入预检。

默认只读取本地配置与候选准入记录，不构造网络客户端。只有指定
``--execute`` 且来源、费用和显式授权门禁全部通过时，CLI 才会把冻结端点
绑定到安全连接器并执行一次受限 Schema 探测；普通调用始终保持零外部 I/O。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
for search_path in (PROJECT_ROOT, SOURCE_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from efficiency_platform_agent.configuration.research import (  # type: ignore[import-untyped]
    ResearchSourceSettings,
)
from efficiency_platform_agent.providers.research.admission_probe import (  # type: ignore[import-untyped]
    LiveSourceProbe,
    LiveSourceProbeTarget,
)
from efficiency_platform_agent.providers.research.transport import (  # type: ignore[import-untyped]
    PinnedHttpConnector,
    TargetResolver,
)
from efficiency_platform_agent.security.url_policy import (
    UrlPolicy,  # type: ignore[import-untyped]
)

type Probe = Callable[[str], Mapping[str, object]]

_REQUIRED_RECORD_FIELDS = {
    "source_id",
    "status",
    "endpoint_url",
    "schema",
    "checked_at",
    "cost_evidence_url",
    "permission_evidence_url",
    "rate_limit",
    "history_range",
    "allowed_storage",
}


def _load_records(path: Path) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("SOURCE_ADMISSION_RECORD_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != "x04-source-admission-candidates/1"
        or not isinstance(payload.get("records"), list)
    ):
        raise ValueError("SOURCE_ADMISSION_RECORD_INVALID")
    records: dict[str, dict[str, object]] = {}
    for raw in payload["records"]:
        if not isinstance(raw, dict) or set(raw) != _REQUIRED_RECORD_FIELDS:
            raise ValueError("SOURCE_ADMISSION_RECORD_INVALID")
        source_id = raw.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in records:
            raise ValueError("SOURCE_ADMISSION_RECORD_INVALID")
        records[source_id] = raw
    return records


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _source_reasons(
    *, config: object, record: dict[str, object] | None, now: datetime
) -> list[str]:
    reasons: list[str] = []
    enabled = getattr(config, "enabled", False)
    cost_mode = getattr(config, "cost_mode", "unknown")
    admission_status = getattr(config, "admission_status", "UNVERIFIED")
    if not enabled:
        reasons.append("SOURCE_DISABLED")
    if cost_mode not in {"free", "free_quota"}:
        reasons.append("SOURCE_COST_UNVERIFIED")
    if admission_status != "VERIFIED":
        reasons.append("SOURCE_CONFIG_UNVERIFIED")
    if record is None:
        reasons.append("SOURCE_ADMISSION_RECORD_MISSING")
        return reasons
    if record["status"] != "VERIFIED":
        reasons.append("SOURCE_RECORD_UNVERIFIED")
    for field in sorted(_REQUIRED_RECORD_FIELDS - {"source_id", "status"}):
        value = record[field]
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"SOURCE_RECORD_FIELD_MISSING:{field}")
    for field in ("endpoint_url", "cost_evidence_url", "permission_evidence_url"):
        value = record[field]
        if isinstance(value, str) and value:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
            ):
                reasons.append(f"SOURCE_RECORD_URL_INVALID:{field}")
    checked_at = _parse_time(record["checked_at"])
    if checked_at is None:
        reasons.append("SOURCE_RECORD_TIME_INVALID")
    elif checked_at > now or now - checked_at > timedelta(days=30):
        reasons.append("SOURCE_RECORD_EXPIRED")
    return reasons


def _load_authorization(
    path: Path | None,
    *,
    now: datetime,
) -> dict[str, object] | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        approved_at = _parse_time(payload.get("approved_at"))
        expires_at = _parse_time(payload.get("expires_at"))
        allowed_actions = payload.get("allowed_actions")
        allowed_sources = payload.get("allowed_source_ids")
        valid = bool(
            payload.get("version") == "x04-source-read-authorization/1"
            and isinstance(payload.get("authorization_id"), str)
            and payload["authorization_id"].strip()
            and isinstance(payload.get("approved_by"), str)
            and payload["approved_by"].strip()
            and approved_at is not None
            and expires_at is not None
            and approved_at <= now < expires_at
            and isinstance(allowed_actions, list)
            and "source_read" in allowed_actions
            and isinstance(allowed_sources, list)
            and allowed_sources
            and all(isinstance(item, str) and item.strip() for item in allowed_sources)
            and len(set(allowed_sources)) == len(allowed_sources)
        )
        return payload if valid else None
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None


def _authorization_allows(
    path: Path | None,
    *,
    source_ids: tuple[str, ...],
    now: datetime,
) -> bool:
    payload = _load_authorization(path, now=now)
    if payload is None:
        return False
    allowed_sources = payload["allowed_source_ids"]
    return isinstance(allowed_sources, list) and set(source_ids).issubset(
        set(allowed_sources)
    )


def create_live_probe(
    *,
    source_config: Path,
    admission_records: Path,
    authorization_file: Path,
    now: datetime | None = None,
    connector: PinnedHttpConnector | None = None,
    resolver: TargetResolver | None = None,
) -> Probe:
    """把已核验且获批的冻结端点绑定到安全连接器；构造过程不联网。"""

    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("PREFLIGHT_NOW_NAIVE")
    authorization = _load_authorization(authorization_file, now=observed_at)
    if authorization is None:
        raise ValueError("SOURCE_READ_AUTHORIZATION_INVALID")
    authorization_id = authorization["authorization_id"]
    allowed_sources = authorization["allowed_source_ids"]
    assert isinstance(authorization_id, str)
    assert isinstance(allowed_sources, list)
    settings = ResearchSourceSettings.load(source_config)
    records = _load_records(admission_records)
    targets: list[LiveSourceProbeTarget] = []
    for config in settings.sources:
        record = records.get(config.source_id)
        if (
            config.source_id not in allowed_sources
            or _source_reasons(config=config, record=record, now=observed_at)
            or record is None
        ):
            continue
        endpoint_url = str(record["endpoint_url"])
        digest = hashlib.sha256(
            f"{authorization_id}\n{config.source_id}\n{endpoint_url}".encode()
        ).hexdigest()
        targets.append(
            LiveSourceProbeTarget(
                source_id=config.source_id,
                adapter_id=config.adapter_id,
                endpoint_url=endpoint_url,
                authorization_scope_digest=digest,
            )
        )
    if not targets:
        raise ValueError("LIVE_SOURCE_PROBE_TARGETS_UNAVAILABLE")
    live_probe = LiveSourceProbe(
        tuple(targets),
        connector=connector,
        resolver=resolver,
        url_policy=UrlPolicy(),
    )

    def run(endpoint_url: str) -> Mapping[str, object]:
        return asyncio.run(live_probe.probe(endpoint_url))

    return run


def build_preflight(
    *,
    source_config: Path,
    admission_records: Path,
    execute: bool = False,
    authorization_file: Path | None = None,
    probe: Probe | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """生成安全预检摘要；只有完整门禁通过后才可能调用注入的 probe。"""

    observed_at = now or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("PREFLIGHT_NOW_NAIVE")
    settings = ResearchSourceSettings.load(source_config)
    records = _load_records(admission_records)
    source_results: list[dict[str, object]] = []
    eligible: list[tuple[str, str]] = []
    for config in settings.sources:
        record = records.get(config.source_id)
        source_reasons = _source_reasons(config=config, record=record, now=observed_at)
        source_results.append(
            {
                "source_id": config.source_id,
                "adapter_id": config.adapter_id,
                "eligible": not source_reasons,
                "reason_codes": source_reasons,
            }
        )
        if not source_reasons and record is not None:
            eligible.append((config.source_id, str(record["endpoint_url"])))

    base: dict[str, Any] = {
        "schema_version": "research-v2-preflight/1",
        "status": "PLAN_ONLY",
        "external_io": False,
        "config_version": settings.config_version,
        "source_count": len(settings.sources),
        "eligible_source_count": len(eligible),
        "probed_source_count": 0,
        "sources": source_results,
        "reason_codes": [],
    }
    if not execute:
        return base

    reasons: list[str] = []
    if not eligible:
        reasons.append("NO_ELIGIBLE_SOURCE")
    source_ids = tuple(source_id for source_id, _ in eligible)
    if not _authorization_allows(
        authorization_file, source_ids=source_ids, now=observed_at
    ):
        reasons.append("AUTHORIZATION_REQUIRED")
    if eligible and probe is None:
        reasons.append("LIVE_SOURCE_PROBE_NOT_BOUND")
    if reasons:
        return {**base, "status": "BLOCKED", "reason_codes": reasons}

    probes: list[dict[str, object]] = []
    assert probe is not None
    for source_id, endpoint_url in eligible:
        try:
            outcome = dict(probe(endpoint_url))
        except Exception:  # noqa: BLE001 - 只输出稳定错误码，不泄露外部异常
            outcome = {"status_code": None, "schema_valid": False}
        probes.append(
            {
                "source_id": source_id,
                "status_code": outcome.get("status_code"),
                "schema_valid": outcome.get("schema_valid") is True,
            }
        )
    passed = all(
        isinstance(item["status_code"], int)
        and 200 <= item["status_code"] < 300
        and item["schema_valid"] is True
        for item in probes
    )
    return {
        **base,
        "status": "PASS" if passed else "FAIL",
        "execution_status": "EXECUTED",
        "external_io": True,
        "probed_source_count": len(probes),
        "probes": probes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-config",
        type=Path,
        default=PROJECT_ROOT / "config/research_sources.toml",
    )
    parser.add_argument(
        "--admission-records",
        type=Path,
        default=PROJECT_ROOT
        / "docs/superpowers/sdd/intent-research-v2/来源准入候选记录.json",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    live_probe: Probe | None = None
    if args.execute and args.authorization_file is not None:
        try:
            live_probe = create_live_probe(
                source_config=args.source_config,
                admission_records=args.admission_records,
                authorization_file=args.authorization_file,
            )
        except ValueError:
            live_probe = None
    result = build_preflight(
        source_config=args.source_config,
        admission_records=args.admission_records,
        execute=args.execute,
        authorization_file=args.authorization_file,
        probe=live_probe,
    )
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if result["status"] in {"PLAN_ONLY", "PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_preflight", "create_live_probe", "main"]
