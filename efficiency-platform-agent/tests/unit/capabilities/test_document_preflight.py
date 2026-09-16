"""文档预检的离线边界测试。"""

import unittest

from efficiency_platform_agent.capabilities.document.contracts import (
    DocumentQualityStatus,
)
from efficiency_platform_agent.capabilities.document.preflight import preflight_document


class DocumentPreflightTests(unittest.TestCase):
    def test_valid_document_accepted(self):
        self.assertEqual(
            preflight_document(b"x", "a.md", "text/markdown").quality_status,
            DocumentQualityStatus.ACCEPTED,
        )

    def test_unsafe_or_oversized_rejected_before_processing(self):
        result = preflight_document(
            b"x" * 11, "../a.pdf", "application/pdf", max_bytes=10
        )
        self.assertEqual(result.quality_status, DocumentQualityStatus.REJECTED)
        self.assertIn("UNSAFE_FILENAME", result.reason_codes)
        self.assertIn("FILE_SIZE_EXCEEDED", result.reason_codes)

    def test_container_signature_and_mime_must_match_extension(self):
        valid = preflight_document(b"%PDF-1.4 synthetic", "a.pdf", "application/pdf")
        self.assertEqual(valid.quality_status, DocumentQualityStatus.ACCEPTED)
        invalid = preflight_document(b"not-png", "a.png", "image/png")
        self.assertEqual(invalid.quality_status, DocumentQualityStatus.REJECTED)
        self.assertIn("SIGNATURE_MISMATCH", invalid.reason_codes)
        wrong_mime = preflight_document(b"%PDF-1.4 synthetic", "a.pdf", "text/plain")
        self.assertIn("MIME_EXTENSION_MISMATCH", wrong_mime.reason_codes)


__all__ = ["DocumentPreflightTests"]
