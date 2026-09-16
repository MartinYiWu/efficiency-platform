"""上传至文档摄取链的离线集成测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.capabilities.document.contracts import (
    DocumentQualityStatus,
)
from efficiency_platform_agent.capabilities.document.docling_parser import DoclingParser
from efficiency_platform_agent.capabilities.document.service import (
    DocumentIngestionService,
)


class UploadDocumentPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_signature_does_not_call_parser(self):
        calls = []
        service = DocumentIngestionService(DoclingParser(lambda *_: calls.append(1)))
        result = await service.ingest(
            b"bad", "signature.exe", "application/octet-stream", "upload-signature"
        )
        self.assertEqual(result.quality_status, DocumentQualityStatus.REJECTED)
        self.assertEqual(calls, [])

    async def test_duplicate_upload_is_not_parsed_again(self):
        calls = []
        service = DocumentIngestionService(
            DoclingParser(lambda *_: calls.append(1) or {"ast": True})
        )
        await service.ingest(b"ok", "note.md", "text/markdown", "upload-1")
        result = await service.ingest(b"ok", "note.md", "text/markdown", "upload-1")
        self.assertEqual(calls, [1])
        self.assertIn("DUPLICATE_UPLOAD", result.reason_codes)


__all__ = ["UploadDocumentPipelineTests"]
