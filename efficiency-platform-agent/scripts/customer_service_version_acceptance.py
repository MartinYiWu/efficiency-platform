"""通过真实 HTTP 接口验收知识版本、回滚和批量失败重试。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx


class AcceptanceFailure(RuntimeError):
    pass


class VersionAcceptance:
    def __init__(
        self,
        base_url: str,
        knowledge_base_id: str,
        document_id: str,
        old_release_id: str,
        agent_id: str,
        agent_version_id: str,
        rag_policy_id: str,
        old_ai_release_id: str,
        evidence_path: Path,
        fixture_dir: Path,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.knowledge_base_id = knowledge_base_id
        self.document_id = document_id
        self.old_release_id = old_release_id
        self.agent_id = agent_id
        self.agent_version_id = agent_version_id
        self.rag_policy_id = rag_policy_id
        self.old_ai_release_id = old_ai_release_id
        self.evidence_path = evidence_path
        self.fixture_dir = fixture_dir
        self.client = httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0))

    def close(self) -> None:
        self.client.close()

    def run(self) -> dict[str, Any]:
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        version = self._upload_v2()
        new_release = self._data(
            self.client.post(
                f"{self.base_url}/api/knowledge/document-versions/{version['id']}/publish"
            )
        )
        new_agent_version, new_ai_release = self._publish_agent_version(new_release["id"])
        new_debug = self._debug(
            new_release["id"], "高风险产品发布的观察期要求是什么？", new_agent_version["id"]
        )
        new_evidence = self._evidence(new_debug)
        if not any("三十分钟观察期" in item.get("excerpt", "") for item in new_evidence):
            raise AcceptanceFailure("V2 检索结果未命中新版本事实")

        rolled_back = self._data(
            self.client.post(
                f"{self.base_url}/api/knowledge/index-releases/{self.old_release_id}/rollback"
            )
        )
        if rolled_back["id"] != self.old_release_id:
            raise AcceptanceFailure("知识索引未回滚到指定版本")
        ai_rollback = self._data(
            self.client.post(
                f"{self.base_url}/api/aihub/agents/customer-service/releases/"
                f"{self.old_ai_release_id}/rollback"
            )
        )
        old_debug = self._debug(
            self.old_release_id, "紧急产品发布需要谁批准？", self.agent_version_id
        )
        old_evidence = self._evidence(old_debug)
        if not any(
            item.get("document_version_id") != version["id"]
            and "产品负责人和技术负责人" in item.get("excerpt", "")
            for item in old_evidence
        ):
            raise AcceptanceFailure("回滚后未检索到旧版本事实")

        batch = self._batch_partial_failure()
        result = {
            "started_and_finished_with_real_http": True,
            "knowledge_version": {
                "document_id": self.document_id,
                "new_version_id": version["id"],
                "new_version_no": version["versionNo"],
                "new_release_id": new_release["id"],
                "new_release_no": new_release["releaseNo"],
                "new_agent_version_id": new_agent_version["id"],
                "new_ai_release_id": new_ai_release["id"],
                "new_debug_run_id": new_debug["debug_run_id"],
                "new_evidence_count": len(new_evidence),
                "rolled_back_release_id": rolled_back["id"],
                "ai_rollback_release_id": ai_rollback["id"],
                "old_debug_run_id": old_debug["debug_run_id"],
                "old_evidence_count": len(old_evidence),
            },
            "batch": batch,
        }
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    def _upload_v2(self) -> dict[str, Any]:
        fixture = self.fixture_dir / "产品发布流程-v2.md"
        acceptance_marker = int(time.time() * 1000)
        fixture.write_text(
            "# 产品发布流程\n\n"
            "产品上线依次经过需求评审、技术评审、测试验收和发布审批。\n\n"
            "紧急发布仍需由产品负责人和技术负责人共同批准，并在次日完成复盘。\n\n"
            "高风险发布必须设置三十分钟观察期，观察期内由发布负责人持续监控核心指标。\n\n"
            f"验收版本追踪标识：{acceptance_marker}\n",
            encoding="utf-8",
        )
        with fixture.open("rb") as stream:
            version = self._data(
                self.client.post(
                    f"{self.base_url}/api/knowledge/documents/{self.document_id}/versions",
                    files={"file": (fixture.name, stream, "text/markdown")},
                    data={"changeSummary": "增加高风险发布观察期要求", "effectiveDate": "2026-10-20"},
                )
            )
        return self._wait_version(version["id"], expected="READY")

    def _batch_partial_failure(self) -> dict[str, Any]:
        valid = self.fixture_dir / "批量导入有效样本.txt"
        invalid = self.fixture_dir / "批量导入损坏样本.pdf"
        valid.write_text(
            "采购审批补充说明：单笔采购超过五万元时需要财务负责人复核。\n"
            f"验收批次追踪标识：{int(time.time() * 1000)}\n",
            encoding="utf-8",
        )
        invalid.write_bytes(
            b"%PDF-1.4\n% deliberately truncated real acceptance fixture\n"
        )
        with valid.open("rb") as good, invalid.open("rb") as bad:
            batch = self._data(
                self.client.post(
                    f"{self.base_url}/api/knowledge/bases/{self.knowledge_base_id}/imports",
                    files=[
                        ("files", (valid.name, good, "text/plain")),
                        ("files", (invalid.name, bad, "application/pdf")),
                    ],
                )
            )
        for item in batch["items"]:
            version_id = item.get("documentVersionId")
            if version_id:
                self._wait_version(version_id)
        completed = self._data(
            self.client.get(f"{self.base_url}/api/knowledge/imports/{batch['id']}")
        )
        if completed["status"] != "PARTIAL_FAILED":
            raise AcceptanceFailure(f"批量导入未形成部分失败: {completed['status']}")
        failed = next(
            (item for item in completed["items"] if item["status"] == "FAILED"), None
        )
        if failed is None:
            raise AcceptanceFailure("批量导入缺少失败项")
        retried = self._data(
            self.client.post(
                f"{self.base_url}/api/knowledge/import-items/{failed['id']}/retry"
            )
        )
        retry_version = retried.get("documentVersionId")
        if not retry_version or retried.get("retryOfItemId") != failed["id"]:
            raise AcceptanceFailure("失败项重试链路未建立")
        retry_result = self._wait_version(retry_version)
        retry_task = retry_result["processingTasks"][0]
        if retry_task["attemptNo"] < 2 or retry_task["status"] != "FAILED":
            raise AcceptanceFailure("损坏文件重试没有形成第二次真实失败记录")
        return {
            "batch_id": completed["id"],
            "status": completed["status"],
            "succeeded_count": completed["succeededCount"],
            "failed_count": completed["failedCount"],
            "failed_item_id": failed["id"],
            "failed_error_code": failed["errorCode"],
            "retry_item_id": retried["id"],
            "retry_attempt_no": retry_task["attemptNo"],
            "retry_status": retry_task["status"],
            "retry_error_code": retry_task["errorCode"],
        }

    def _wait_version(self, version_id: str, expected: str | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + 180
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            latest = self._data(
                self.client.get(
                    f"{self.base_url}/api/knowledge/document-versions/{version_id}"
                )
            )
            tasks = latest.get("processingTasks") or []
            if tasks:
                task = self._data(
                    self.client.get(
                        f"{self.base_url}/api/knowledge/processing-tasks/{tasks[0]['id']}"
                    )
                )
                if task["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    latest = self._data(
                        self.client.get(
                            f"{self.base_url}/api/knowledge/document-versions/{version_id}"
                        )
                    )
                    if expected is not None and latest["status"] != expected:
                        raise AcceptanceFailure(
                            f"版本 {version_id} 状态为 {latest['status']}，预期 {expected}"
                        )
                    return latest
            time.sleep(1)
        raise AcceptanceFailure(f"版本处理超时: {version_id}, 最新状态={latest.get('status')}")

    def _publish_agent_version(
        self, index_release_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        detail = self._data(
            self.client.get(f"{self.base_url}/api/aihub/agents/{self.agent_id}")
        )
        source = next(
            (
                version
                for version in detail["versions"]
                if version["id"] == self.agent_version_id
            ),
            None,
        )
        if source is None:
            raise AcceptanceFailure("未找到源 Agent 版本")
        created = self._data(
            self.client.post(
                f"{self.base_url}/api/aihub/agents/{self.agent_id}/versions",
                json={
                    "semanticVersion": f"1.0.{int(time.time())}",
                    "graphKey": source["graphKey"],
                    "graphVersion": source["graphVersion"],
                    "changeSummary": "真实验收：切换到产品发布流程新索引",
                    "sourceVersionId": self.agent_version_id,
                },
            )
        )
        self._data(
            self.client.put(
                f"{self.base_url}/api/aihub/agents/versions/{created['id']}/knowledge-bindings",
                json={
                    "bindings": [
                        {
                            "knowledgeBaseId": self.knowledge_base_id,
                            "indexReleaseId": index_release_id,
                            "priority": 1,
                            "required": True,
                        }
                    ]
                },
            )
        )
        validated = self._data(
            self.client.post(
                f"{self.base_url}/api/aihub/agents/versions/{created['id']}/transition",
                json={"status": "VALIDATED"},
            )
        )
        release = self._data(
            self.client.post(
                f"{self.base_url}/api/aihub/agents/customer-service/versions/"
                f"{created['id']}/release",
                json={"environment": "dev"},
            )
        )
        if validated["status"] != "VALIDATED" or release["releaseStatus"] != "ACTIVE":
            raise AcceptanceFailure("新 Agent 版本未完成发布")
        return created, release

    def _debug(
        self, release_id: str, question: str, agent_version_id: str
    ) -> dict[str, Any]:
        value = self._data(
            self.client.post(
                f"{self.base_url}/api/aihub/rag-debug-runs",
                json={
                    "agentKey": "customer-service",
                    "question": question,
                    "agentVersionId": agent_version_id,
                    "ragPolicyVersionId": self.rag_policy_id,
                    "knowledgeBindings": [
                        {
                            "knowledgeBaseId": self.knowledge_base_id,
                            "indexReleaseId": release_id,
                        }
                    ],
                },
            )
        )
        if value["status"] != "SUCCEEDED":
            raise AcceptanceFailure(f"RAG 调试失败: {value.get('errorCode')}")
        persisted = self._data(
            self.client.get(
                f"{self.base_url}/api/aihub/rag-debug-runs/{value['debug_run_id']}"
            )
        )
        if (
            persisted.get("debug_run_id") != value.get("debug_run_id")
            or persisted.get("status") != value.get("status")
            or [item.get("chunk_id") for item in self._evidence(persisted)]
            != [item.get("chunk_id") for item in self._evidence(value)]
        ):
            raise AcceptanceFailure("RAG 调试结果未被一致持久化")
        return value

    @staticmethod
    def _evidence(debug: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            evidence
            for stage in debug.get("stages") or []
            for evidence in stage.get("evidence") or []
        ]

    @staticmethod
    def _data(response: httpx.Response) -> Any:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcceptanceFailure(f"HTTP {response.status_code} 返回非 JSON") from error
        if response.status_code >= 400 or payload.get("code") != "SUCCESS":
            raise AcceptanceFailure(
                f"HTTP {response.status_code}: {payload.get('code') or payload.get('message')}"
            )
        return payload["data"]


def main() -> None:
    parser = argparse.ArgumentParser(description="执行知识版本与批量导入真实验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--old-release-id", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--agent-version-id", required=True)
    parser.add_argument("--rag-policy-id", required=True)
    parser.add_argument("--old-ai-release-id", required=True)
    parser.add_argument(
        "--evidence-path", default=".local-acceptance/customer-service/version-batch.json"
    )
    parser.add_argument(
        "--fixture-dir", default=".local-acceptance/customer-service/version-files"
    )
    args = parser.parse_args()
    acceptance = VersionAcceptance(
        args.base_url,
        args.knowledge_base_id,
        args.document_id,
        args.old_release_id,
        args.agent_id,
        args.agent_version_id,
        args.rag_policy_id,
        args.old_ai_release_id,
        Path(args.evidence_path),
        Path(args.fixture_dir),
    )
    try:
        result = acceptance.run()
    finally:
        acceptance.close()
    print(
        json.dumps(
            {
                "new_release_id": result["knowledge_version"]["new_release_id"],
                "rolled_back_release_id": result["knowledge_version"]["rolled_back_release_id"],
                "batch_status": result["batch"]["status"],
                "retry_status": result["batch"]["retry_status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
