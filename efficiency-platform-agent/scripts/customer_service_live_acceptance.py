"""智能客服真实 HTTP 验收编排；只记录脱敏证据，不读取或输出凭据。"""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class AcceptanceConfig:
    java_base_url: str
    agent_base_url: str
    knowledge_base_id: str
    evidence_path: Path
    fixture_dir: Path


class AcceptanceFailure(RuntimeError):
    """真实响应不满足产品契约。"""


class LiveAcceptance:
    def __init__(self, config: AcceptanceConfig) -> None:
        self.config = config
        self.client = httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
        self.evidence: dict[str, Any] = {
            "started_at_epoch_ms": int(time.time() * 1000),
            "services": {},
            "uploads": [],
        }

    def run_upload_matrix(self) -> dict[str, Any]:
        self._health()
        fixtures = create_fixtures(self.config.fixture_dir)
        for fixture in fixtures:
            self.evidence["uploads"].append(self._upload_and_wait(fixture))
        self.evidence["finished_at_epoch_ms"] = int(time.time() * 1000)
        self._write_evidence()
        return self.evidence

    def _health(self) -> None:
        checks = {
            "java": f"{self.config.java_base_url}/actuator/health",
            "agent": f"{self.config.agent_base_url}/health/live",
        }
        for name, url in checks.items():
            response = self.client.get(url)
            response.raise_for_status()
            self.evidence["services"][name] = {"status_code": response.status_code}

    def _upload_and_wait(self, fixture: Path) -> dict[str, Any]:
        content_type = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
        }[fixture.suffix.lower()]
        with fixture.open("rb") as stream:
            response = self.client.post(
                f"{self.config.java_base_url}/api/knowledge/bases/"
                f"{self.config.knowledge_base_id}/documents/upload",
                files={"file": (fixture.name, stream, content_type)},
            )
        payload = _business_data(response)
        item = payload["items"][0]
        if not item.get("documentVersionId"):
            raise AcceptanceFailure(f"{fixture.name} 未生成文档版本")
        version_id = item["documentVersionId"]
        deadline = time.monotonic() + 180
        latest: dict[str, Any] = {}
        task_id: str | None = None
        while time.monotonic() < deadline:
            latest = _business_data(
                self.client.get(
                    f"{self.config.java_base_url}/api/knowledge/document-versions/{version_id}"
                )
            )
            tasks = latest.get("processingTasks") or []
            if tasks:
                task_id = task_id or tasks[0]["id"]
                task = _business_data(
                    self.client.get(
                        f"{self.config.java_base_url}/api/knowledge/processing-tasks/{task_id}"
                    )
                )
                if task["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    latest = _business_data(
                        self.client.get(
                            f"{self.config.java_base_url}/api/knowledge/document-versions/{version_id}"
                        )
                    )
                    if task["status"] != "SUCCEEDED" or latest["status"] != "READY":
                        raise AcceptanceFailure(
                            f"{fixture.name} 处理失败: "
                            f"{task.get('errorCode') or task['status']}"
                        )
                    return {
                        "file_name": fixture.name,
                        "content_type": content_type,
                        "document_id": item["documentId"],
                        "document_version_id": version_id,
                        "processing_task_id": task["id"],
                        "agent_task_id": task["agentTaskId"],
                        "status": task["status"],
                        "stage": task["stage"],
                        "progress_percent": task["progressPercent"],
                    }
            time.sleep(1)
        raise AcceptanceFailure(
            f"{fixture.name} 处理超时，最后状态={latest.get('status')}"
        )

    def _write_evidence(self) -> None:
        self.config.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.evidence_path.write_text(
            json.dumps(self.evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _business_data(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError as error:
        raise AcceptanceFailure(
            f"HTTP {response.status_code} 返回非 JSON 响应"
        ) from error
    if response.status_code >= 400:
        raise AcceptanceFailure(
            f"HTTP {response.status_code}: {payload.get('code') or payload.get('error')}"
        )
    if isinstance(payload, dict) and "code" in payload:
        if payload.get("code") != "SUCCESS":
            raise AcceptanceFailure(f"业务失败: {payload.get('code')}")
        return payload.get("data")
    return payload


def create_fixtures(directory: Path) -> tuple[Path, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    policy = (
        "远光科技差旅管理制度（真实接口验收样本）\n"
        "员工出差前必须在内部系统提交申请，由直属负责人审批。\n"
        "国内住宿标准为每晚六百元以内，超出标准必须补充书面说明。\n"
        "差旅结束后十个工作日内提交报销，发票和行程单必须完整。\n"
        "本制度自二〇二六年十月二十日起生效。\n"
    )
    txt = directory / "公司差旅制度.txt"
    txt.write_text(policy, encoding="utf-8")
    markdown = directory / "产品发布流程.md"
    markdown.write_text(
        "# 产品发布流程\n\n"
        "产品上线依次经过需求评审、技术评审、测试验收和发布审批。\n\n"
        "紧急发布仍需由产品负责人和技术负责人共同批准，并在次日完成复盘。\n",
        encoding="utf-8",
    )
    html = directory / "技术故障升级规范.html"
    html.write_text(
        "<!doctype html><html><head><title>技术故障升级规范</title></head>"
        "<body><h1>技术故障升级规范</h1><p>P1 故障发现后五分钟内通知值班负责人，"
        "十五分钟内建立处置群，恢复后两个工作日内完成复盘。</p></body></html>",
        encoding="utf-8",
    )
    docx = directory / "客户需求评审流程.docx"
    _write_docx(
        docx,
        "客户需求评审流程",
        "客户需求由业务负责人登记，产品、研发和交付共同评估范围、风险与排期。"
        "评审结论必须记录负责人和下一步动作。",
    )
    pdf = directory / "信息安全事件报告制度.pdf"
    _write_pdf(
        pdf,
        "Information Security Incident Policy",
        "Security incidents must be reported to the security owner within 30 minutes. "
        "Evidence must be preserved and an incident review must be completed within three workdays.",
    )
    return txt, markdown, html, docx, pdf


def _write_docx(path: Path, title: str, paragraph: str) -> None:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{title}</w:t></w:r></w:p>"
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document)


def _write_pdf(path: Path, title: str, paragraph: str) -> None:
    text = f"BT /F1 16 Tf 72 740 Td ({_pdf_escape(title)}) Tj 0 -30 Td /F1 11 Tf ({_pdf_escape(paragraph)}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(text.encode('latin-1'))} >>\nstream\n{text}\nendstream",
    ]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n{value}\nendobj\n".encode("latin-1"))
    xref = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    body.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(body)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行智能客服真实上传验收")
    parser.add_argument("--java-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--agent-base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument(
        "--evidence-path", default=".local-acceptance/customer-service-live.json"
    )
    parser.add_argument(
        "--fixture-dir", default=".local-acceptance/customer-service-files"
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    config = AcceptanceConfig(
        java_base_url=arguments.java_base_url.rstrip("/"),
        agent_base_url=arguments.agent_base_url.rstrip("/"),
        knowledge_base_id=arguments.knowledge_base_id,
        evidence_path=Path(arguments.evidence_path),
        fixture_dir=Path(arguments.fixture_dir),
    )
    result = LiveAcceptance(config).run_upload_matrix()
    print(
        json.dumps(
            {
                "service_count": len(result["services"]),
                "upload_count": len(result["uploads"]),
                "statuses": [item["status"] for item in result["uploads"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
