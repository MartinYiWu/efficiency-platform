"""通过 Java 公开 HTTP 接口执行智能客服真实对话验收。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


class AcceptanceFailure(RuntimeError):
    pass


class ChatAcceptance:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0))

    def close(self) -> None:
        self.client.close()

    def run_scenario(
        self,
        name: str,
        question: str,
        expected_mode: str,
        required_text: tuple[str, ...] = (),
        *,
        citations_required: bool,
    ) -> dict[str, Any]:
        conversation = self._data(
            self.client.post(
                f"{self.base_url}/api/customer-service/conversations",
                json={"title": f"真实验收-{name}"},
            )
        )
        conversation_id = conversation["id"]
        submitted = self._data(
            self.client.post(
                f"{self.base_url}/api/customer-service/conversations/"
                f"{conversation_id}/messages",
                json={
                    "contractVersion": "customer-service-message/1",
                    "message": question,
                    "clientRequestId": f"live-{name}-{uuid4()}",
                },
            )
        )
        run_id = submitted["runId"]
        events = self._events(run_id)
        terminal = events[-1]
        if terminal["event"] != "run.completed":
            raise AcceptanceFailure(f"{name} 未成功: {terminal}")
        if terminal["data"].get("answerMode") != expected_mode:
            raise AcceptanceFailure(
                f"{name} 模式错误: {terminal['data'].get('answerMode')}"
            )

        replay = self._data(
            self.client.get(f"{self.base_url}/api/aihub/runs/{run_id}/replay")
        )
        answer = replay.get("answer") or {}
        content = answer.get("content") or ""
        if replay["run"]["status"] != "SUCCEEDED":
            raise AcceptanceFailure(f"{name} 回放状态不是 SUCCEEDED")
        if replay["run"]["answerMode"] != expected_mode:
            raise AcceptanceFailure(f"{name} 回放模式与 SSE 不一致")
        for expected in required_text:
            if expected not in content:
                raise AcceptanceFailure(f"{name} 缺少预期文本: {expected}")
        citations = replay.get("citations") or []
        if citations_required and not citations:
            raise AcceptanceFailure(f"{name} 缺少引用")
        if not citations_required and citations:
            raise AcceptanceFailure(f"{name} 不应返回引用")

        resumed = self._events(run_id, after_sequence=max(0, events[-1]["id"] - 2))
        if not resumed or any(
            item["id"] <= events[-1]["id"] - 2 for item in resumed
        ):
            raise AcceptanceFailure(f"{name} SSE 续传序列不正确")
        return {
            "name": name,
            "conversation_id": conversation_id,
            "run_id": run_id,
            "answer_message_id": answer.get("id"),
            "answer_mode": expected_mode,
            "answer": content,
            "citation_count": len(citations),
            "event_count": len(events),
            "last_sequence": events[-1]["id"],
            "resume_sequences": [item["id"] for item in resumed],
        }

    def feedback(
        self, message_id: str, rating: str, reason_code: str | None = None
    ) -> dict[str, Any]:
        value = self._data(
            self.client.put(
                f"{self.base_url}/api/customer-service/messages/{message_id}/feedback",
                json={
                    "rating": rating,
                    "reasonCode": reason_code,
                    "comment": None,
                },
            )
        )
        if value["rating"] != rating:
            raise AcceptanceFailure("反馈未按请求持久化")
        return {
            "message_id": message_id,
            "feedback_id": value["id"],
            "rating": value["rating"],
            "reason_code": value.get("reasonCode"),
        }

    def cancel(self) -> dict[str, Any]:
        conversation = self._data(
            self.client.post(
                f"{self.base_url}/api/customer-service/conversations",
                json={"title": "真实验收-取消"},
            )
        )
        conversation_id = conversation["id"]
        submitted = self._data(
            self.client.post(
                f"{self.base_url}/api/customer-service/conversations/"
                f"{conversation_id}/messages",
                json={
                    "contractVersion": "customer-service-message/1",
                    "message": "请详细说明公司的产品发布流程并逐项给出依据。",
                    "clientRequestId": f"live-cancel-{uuid4()}",
                },
            )
        )
        run_id = submitted["runId"]
        self._data(
            self.client.post(
                f"{self.base_url}/api/customer-service/runs/{run_id}/cancel"
            )
        )
        events = self._events(run_id)
        if events[-1]["event"] != "run.cancelled":
            raise AcceptanceFailure(f"取消未生效: {events[-1]}")
        run = self._data(
            self.client.get(f"{self.base_url}/api/customer-service/runs/{run_id}")
        )
        if run["status"] != "CANCELLED":
            raise AcceptanceFailure(f"取消状态未投影: {run['status']}")
        return {
            "conversation_id": conversation_id,
            "run_id": run_id,
            "status": run["status"],
            "last_sequence": events[-1]["id"],
        }

    def _events(self, run_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        current: dict[str, str] = {}
        with self.client.stream(
            "GET",
            f"{self.base_url}/api/customer-service/runs/{run_id}/events",
            params={"afterSequence": after_sequence},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    key, value = line.split(":", 1)
                    current[key] = value.strip()
                    continue
                if current:
                    values.append(
                        {
                            "id": int(current["id"]),
                            "event": current["event"],
                            "data": json.loads(current["data"]),
                        }
                    )
                    current = {}
        if current:
            values.append(
                {
                    "id": int(current["id"]),
                    "event": current["event"],
                    "data": json.loads(current["data"]),
                }
            )
        if not values:
            raise AcceptanceFailure(f"Run {run_id} 未返回 SSE 事件")
        sequences = [item["id"] for item in values]
        if sequences != sorted(set(sequences)):
            raise AcceptanceFailure(f"Run {run_id} SSE 序列不单调")
        return values

    @staticmethod
    def _data(response: httpx.Response) -> Any:
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "SUCCESS":
            raise AcceptanceFailure(str(payload))
        return payload["data"]


def main() -> None:
    parser = argparse.ArgumentParser(description="执行智能客服真实对话验收")
    parser.add_argument("--java-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    acceptance = ChatAcceptance(args.java_base_url)
    try:
        scenarios = [
            acceptance.run_scenario(
                "company",
                "员工国内出差住宿标准是多少？报销需要在多久内完成？",
                "COMPANY_KNOWLEDGE",
                ("六百元", "十个工作日"),
                citations_required=True,
            ),
            acceptance.run_scenario(
                "general",
                "请给我一些提升日常会议效率的通用建议。",
                "GENERAL_ADVICE",
                ("通用建议，非公司制度",),
                citations_required=False,
            ),
            acceptance.run_scenario(
                "mixed",
                "根据公司的产品发布流程说明必经步骤，并补充一些通用的发布风险控制建议。",
                "MIXED",
                ("通用建议，非公司制度",),
                citations_required=True,
            ),
            acceptance.run_scenario(
                "clarify",
                "这个应该怎么处理？",
                "CLARIFY",
                citations_required=False,
            ),
            acceptance.run_scenario(
                "insufficient",
                "公司规定员工每年有多少天带薪病假？",
                "INSUFFICIENT_EVIDENCE",
                citations_required=False,
            ),
        ]
        up = acceptance.feedback(scenarios[0]["answer_message_id"], "UP")
        down = acceptance.feedback(
            scenarios[2]["answer_message_id"], "DOWN", "UNCLEAR"
        )
        evidence = {
            "contract_version": "customer-service-live-acceptance/1",
            "scenarios": scenarios,
            "feedback": [up, down],
            "cancel": acceptance.cancel(),
        }
        output = json.dumps(evidence, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        print(output)
    finally:
        acceptance.close()


if __name__ == "__main__":
    main()
