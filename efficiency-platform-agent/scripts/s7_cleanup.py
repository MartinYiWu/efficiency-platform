"""S7 验收产物的精确清理脚本。"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

_SCHEMA_PATTERN = re.compile(r"^s7_acceptance_[a-f0-9]{8}$")
_REDIS_PREFIX_PATTERN = re.compile(r"^s7:[A-Za-z0-9._-]+:$")
_COS_PREFIX_PATTERN = re.compile(r"^s7/[A-Za-z0-9._-]+/$")


def _read_manifest(
    manifest_path: Path, *, require_version: bool = False
) -> dict[str, object]:
    """读取并校验清理清单的基础结构。"""
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("清理清单格式无效") from error
    if not isinstance(data, dict):
        raise TypeError("清理清单格式无效")
    if require_version and data.get("version") != "s7-cleanup-manifest/1":
        raise ValueError("清理清单版本无效")
    return data


def validate_external_cleanup_manifest(data: object) -> dict[str, object]:
    """校验数据库、Redis、COS 清理目标均为精确 S7 范围。"""
    if not isinstance(data, dict):
        raise TypeError("清理清单格式无效")
    external = data.get("external", {})
    if external is None:
        external = {}
    if not isinstance(external, dict):
        raise TypeError("外部清理清单格式无效")
    schema = external.get("postgres_schema")
    if schema is not None and (
        not isinstance(schema, str) or _SCHEMA_PATTERN.fullmatch(schema) is None
    ):
        raise ValueError("PostgreSQL 清理 Schema 必须是精确 S7 Schema")
    redis_prefixes = external.get("redis_prefixes", [])
    if not isinstance(redis_prefixes, list) or any(
        not isinstance(prefix, str) or _REDIS_PREFIX_PATTERN.fullmatch(prefix) is None
        for prefix in redis_prefixes
    ):
        raise ValueError("Redis 清理前缀必须是精确 S7 前缀")
    cos_prefixes = external.get("cos_prefixes", [])
    if not isinstance(cos_prefixes, list) or any(
        not isinstance(prefix, str) or _COS_PREFIX_PATTERN.fullmatch(prefix) is None
        for prefix in cos_prefixes
    ):
        raise ValueError("COS 清理前缀必须是精确 S7 前缀")
    forbidden = {"flushdb", "flushall", "*", "all", "database"}
    if any(str(key).lower() in forbidden for key in external):
        raise ValueError("禁止使用全局清理动作")
    return {
        "postgres_schema": schema,
        "redis_prefixes": list(redis_prefixes),
        "cos_prefixes": list(cos_prefixes),
    }


def cleanup_external_targets(
    manifest_path: Path,
    *,
    postgres_cleaner: Callable[[str], Mapping[str, object]] | None = None,
    redis_cleaner: Callable[[str], Mapping[str, object]] | None = None,
    cos_cleaner: Callable[[str], Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """通过注入的清理器执行精确外部目标，不自行创建网络客户端。"""
    try:
        data = _read_manifest(manifest_path, require_version=True)
        targets = validate_external_cleanup_manifest(data)
    except FileNotFoundError:
        return {
            "status": "NOT_EXECUTED",
            "reason": "manifest_missing",
            "external_cleanup_executed": False,
        }
    except (TypeError, ValueError) as error:
        return {
            "status": "FAILED",
            "reason": str(error),
            "external_cleanup_executed": False,
        }

    schema = cast(str | None, targets["postgres_schema"])
    redis_prefixes = cast(list[str], targets["redis_prefixes"])
    cos_prefixes = cast(list[str], targets["cos_prefixes"])
    if schema is not None and postgres_cleaner is None:
        return {
            "status": "NOT_EXECUTED",
            "reason": "external_cleaner_missing",
            "external_cleanup_executed": False,
        }
    if redis_prefixes and redis_cleaner is None:
        return {
            "status": "NOT_EXECUTED",
            "reason": "external_cleaner_missing",
            "external_cleanup_executed": False,
        }
    if cos_prefixes and cos_cleaner is None:
        return {
            "status": "NOT_EXECUTED",
            "reason": "external_cleaner_missing",
            "external_cleanup_executed": False,
        }

    calls: list[dict[str, object]] = []
    try:
        if schema is not None and postgres_cleaner is not None:
            calls.append(
                {
                    "kind": "postgres_schema",
                    "target": schema,
                    "result": dict(postgres_cleaner(schema)),
                }
            )
        if redis_cleaner is not None:
            for prefix in redis_prefixes:
                calls.append(
                    {
                        "kind": "redis_prefix",
                        "target": prefix,
                        "result": dict(redis_cleaner(prefix)),
                    }
                )
        if cos_cleaner is not None:
            for prefix in cos_prefixes:
                calls.append(
                    {
                        "kind": "cos_prefix",
                        "target": prefix,
                        "result": dict(cos_cleaner(prefix)),
                    }
                )
    except Exception as error:  # noqa: BLE001, 清理失败必须覆盖业务结论
        return {
            "status": "FAILED",
            "reason": "external_cleanup_failed",
            "error_type": type(error).__name__,
            "external_cleanup_executed": True,
            "cleanup_ok": False,
            "calls": calls,
        }
    return {
        "status": "CLEANED",
        "external_cleanup_executed": True,
        "cleanup_ok": True,
        "calls": calls,
    }


def cleanup_manifest(manifest_path: Path) -> dict[str, object]:
    """仅删除 manifest 声明且位于其目录内的本地文件。"""
    if not manifest_path.is_file():
        return {"status": "NOT_EXECUTED", "reason": "manifest_missing", "removed": 0}
    data = _read_manifest(manifest_path)
    external_targets = validate_external_cleanup_manifest(data)
    local_paths = data.get("local_paths", [])
    if not isinstance(local_paths, list) or any(
        not isinstance(raw_path, str) or not raw_path.strip()
        for raw_path in local_paths
    ):
        raise ValueError("清理清单格式无效")  # 清单结构错误统一为值错误
    root = manifest_path.parent.resolve()
    removed = 0
    for raw_path in local_paths:
        target = Path(raw_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("清理路径必须位于 manifest 目录内") from exc
        if target == manifest_path.resolve():
            continue
        if target.exists() and not target.is_file():
            raise ValueError("清理目标必须是文件")  # 清理目标类型错误统一为值错误
        if target.is_file() or target.is_symlink():
            target.unlink()
            removed += 1
    redis_targets = cast(list[str], external_targets["redis_prefixes"])
    cos_targets = cast(list[str], external_targets["cos_prefixes"])
    return {
        "status": "CLEANED",
        "removed": removed,
        "external_prefixes": redis_targets + cos_targets,
        "external_cleanup_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    """命令行入口，不执行数据库或缓存全局清理。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(cleanup_manifest(args.manifest), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "cleanup_external_targets",
    "cleanup_manifest",
    "main",
    "validate_external_cleanup_manifest",
]
