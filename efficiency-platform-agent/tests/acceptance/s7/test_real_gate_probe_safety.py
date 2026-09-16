"""验证各真实 Gate 关闭时不会创建外部客户端。"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.s7_verify import (
    probe_cos_artifact,
    probe_deepseek_web_search,
    probe_postgres_pgvector,
    probe_redis_taskiq,
    run_cos_artifact_acceptance,
    run_deepseek_web_search_acceptance,
    run_postgres_pgvector_acceptance,
    run_redis_taskiq_acceptance,
)


class RealGateProbeSafetyTests(unittest.IsolatedAsyncioTestCase):
    """真实探测入口的默认关闭安全边界。"""

    approval_file = Path("docs/superpowers/sdd/operation-acceptance-s7/授权记录.json")

    async def test_redis_probe_is_closed_by_default(self) -> None:
        result = await probe_redis_taskiq(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertIn(
            result["reason"],
            {"gate_disabled", "network_probe_authorization_missing"},
        )
        self.assertFalse(result["external_io"])

    async def test_cos_probe_is_closed_by_default(self) -> None:
        result = await probe_cos_artifact(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertIn(
            result["reason"],
            {"gate_disabled", "charged_acceptance_authorization_missing"},
        )
        self.assertFalse(result["external_io"])

    async def test_redis_write_acceptance_is_closed_by_default(self) -> None:
        result = await run_redis_taskiq_acceptance(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertEqual(result["reason"], "gate_disabled")
        self.assertFalse(result["external_io"])

    async def test_cos_write_acceptance_is_closed_by_default(self) -> None:
        result = await run_cos_artifact_acceptance(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertEqual(result["reason"], "gate_disabled")
        self.assertFalse(result["external_io"])

    async def test_postgres_probe_is_closed_by_default(self) -> None:
        result = await probe_postgres_pgvector(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertEqual(result["reason"], "gate_disabled")
        self.assertFalse(result["external_io"])

    async def test_postgres_write_acceptance_is_closed_by_default(self) -> None:
        result = await run_postgres_pgvector_acceptance(
            approval_file=self.approval_file
        )
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertEqual(result["reason"], "gate_disabled")
        self.assertFalse(result["external_io"])

    async def test_web_search_probe_is_closed_by_default(self) -> None:
        result = await probe_deepseek_web_search(approval_file=self.approval_file)
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertIn(
            result["reason"],
            {"gate_disabled", "network_probe_authorization_missing"},
        )
        self.assertFalse(result["external_io"])

    async def test_web_search_acceptance_is_closed_by_default(self) -> None:
        result = await run_deepseek_web_search_acceptance(
            approval_file=self.approval_file
        )
        self.assertEqual(result["status"], "NOT_EXECUTED")
        self.assertIn(
            result["reason"],
            {"gate_disabled", "charged_acceptance_authorization_missing"},
        )
        self.assertFalse(result["external_io"])


__all__ = ["RealGateProbeSafetyTests"]
