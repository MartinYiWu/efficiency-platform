"""X04 旧真实模型评测入口已禁用，须使用受保护的 Java/Agent 入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import selectors
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
for search_path in (PROJECT_ROOT, SOURCE_ROOT):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))


def _run_async(coroutine):
    if sys.platform == "win32":
        return asyncio.run(
            coroutine,
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    return asyncio.run(coroutine)


async def execute_cluster_evaluation(
    *,
    authorization_file: Path,
    tenant_id: str,
    request_id: str,
    approved_budget_microunits: int,
    database_url: str,
    env_file: Path,
    manifest_file: Path,
) -> dict[str, object]:
    """旧入口禁用；真实付费请求须切换到受保护的 Java/Agent 入口。"""
    raise RuntimeError("PAID_LEGACY_ENTRY_DISABLED: use protected Java/Agent entry")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--approved-budget-microunits", type=int, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument(
        "--manifest-file",
        type=Path,
        default=PROJECT_ROOT / "tests/fixtures/research_v2/corpus_manifest.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = _run_async(
            execute_cluster_evaluation(
                authorization_file=args.authorization_file,
                tenant_id=args.tenant_id,
                request_id=args.request_id,
                approved_budget_microunits=args.approved_budget_microunits,
                database_url=args.database_url,
                env_file=args.env_file,
                manifest_file=args.manifest_file,
            )
        )
    except Exception as exc:  # noqa: BLE001 - CLI 只暴露稳定异常类型
        result = {
            "schema_version": "research-v2-cluster-evaluation/1",
            "status": "BLOCKED",
            "reason_codes": [type(exc).__name__],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "precision": (result.get("metrics") or {}).get("precision")
                if isinstance(result.get("metrics"), dict)
                else None,
                "recall": (result.get("metrics") or {}).get("recall")
                if isinstance(result.get("metrics"), dict)
                else None,
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
