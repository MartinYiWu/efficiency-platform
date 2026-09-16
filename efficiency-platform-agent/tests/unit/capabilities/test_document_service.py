"""文档摄取离线边界测试。"""

import unittest
from pathlib import Path
from unittest.mock import patch

from efficiency_platform_agent.capabilities.document.contracts import (
    DocumentQualityStatus,
)
from efficiency_platform_agent.capabilities.document.docling_parser import DoclingParser
from efficiency_platform_agent.capabilities.document.service import (
    DocumentIngestionService,
)


class DocumentServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_default_docling_parser_reads_local_markdown(self):
        fixture = Path(__file__).parents[2] / "fixtures" / "s7" / "plain_text_v1.md"
        content = fixture.read_bytes()
        parser = DoclingParser()
        result = parser.parse(content, fixture.name)
        self.assertEqual(result["kind"], "docling_markdown")
        self.assertIn("青禾实验室", result["text"])

    def test_default_pdf_parser_fails_closed_without_explicit_pipeline(self):
        class UnexpectedConverter:
            def __init__(self, **_kwargs):
                raise AssertionError("不应初始化默认 PDF 管线")

        parser = DoclingParser()
        with (
            patch("docling.document_converter.DocumentConverter", UnexpectedConverter),
            self.assertRaisesRegex(RuntimeError, "DOCLING_PDF_PIPELINE_REQUIRED"),
        ):
            parser.parse(b"%PDF-synthetic", "source.pdf")

    async def test_rejected_input_does_not_parse_or_index(self):
        calls = []
        service = DocumentIngestionService(
            DoclingParser(lambda *_: calls.append(1)), indexer=lambda _: calls.append(2)
        )
        result = await service.ingest(
            b"x", "../bad.exe", "application/octet-stream", "u1"
        )
        self.assertEqual(result.quality_status, DocumentQualityStatus.REJECTED)
        self.assertEqual(calls, [])
        self.assertEqual(service._processed, set())

    async def test_same_upload_is_not_parsed_twice(self):
        calls = []
        service = DocumentIngestionService(
            DoclingParser(lambda *_: calls.append(1) or {"ast": 1})
        )
        await service.ingest(b"x", "a.md", "text/markdown", "u1")
        duplicate = await service.ingest(b"x", "a.md", "text/markdown", "u1")
        self.assertEqual(calls, [1])
        self.assertIn("DUPLICATE_UPLOAD", duplicate.reason_codes)

    async def test_failed_processing_does_not_poison_upload_retry(self):
        calls = []

        class FlakyParser:
            def parse(self, *_args):
                calls.append("parse")
                if len(calls) == 1:
                    raise RuntimeError("解析失败")
                return {"ast": "ok"}

        service = DocumentIngestionService(FlakyParser())
        with self.assertRaisesRegex(RuntimeError, "解析失败"):
            await service.ingest("正文".encode(), "a.md", "text/markdown", "retry-1")

        result = await service.ingest(
            "正文".encode(), "a.md", "text/markdown", "retry-1"
        )

        self.assertEqual(calls, ["parse", "parse"])
        self.assertEqual(result.document_ast, {"ast": "ok"})


__all__ = ["DocumentServiceTests"]
