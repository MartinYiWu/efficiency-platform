"""文档输入预检；失败时不调用解析器或 Artifact。"""

from __future__ import annotations

import io
from pathlib import PurePath

from .contracts import DocumentPreflightResult, DocumentQualityStatus


def preflight_document(
    content: bytes, filename: str, mime_type: str, *, max_bytes: int = 10 * 1024 * 1024
) -> DocumentPreflightResult:
    """校验扩展名、MIME、大小和路径安全。"""
    extension = PurePath(filename).suffix.lower()
    reasons: list[str] = []
    if (
        not filename
        or PurePath(filename).name != filename
        or ".." in PurePath(filename).parts
    ):
        reasons.append("UNSAFE_FILENAME")
    if not isinstance(content, bytes) or len(content) > max_bytes:
        reasons.append("FILE_SIZE_EXCEEDED")
    allowed = {
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
        ".json",
        ".parquet",
        ".png",
        ".jpg",
        ".jpeg",
        ".md",
        ".txt",
    }
    if extension not in allowed:
        reasons.append("UNSUPPORTED_EXTENSION")
    if not isinstance(mime_type, str) or not mime_type.strip():
        reasons.append("MIME_MISSING")
    normalized_mime = mime_type.split(";", 1)[0].strip().lower()
    expected_mimes = {
        ".pdf": {"application/pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        },
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".csv": {"text/csv", "application/csv"},
        ".json": {"application/json", "text/json"},
        ".parquet": {"application/vnd.apache.parquet", "application/octet-stream"},
        ".md": {"text/markdown", "text/plain"},
        ".txt": {"text/plain"},
    }
    if extension in expected_mimes and normalized_mime not in expected_mimes[extension]:
        reasons.append("MIME_EXTENSION_MISMATCH")
    signatures = {
        ".pdf": (b"%PDF-",),
        ".docx": (b"PK",),
        ".xlsx": (b"PK",),
        ".parquet": (b"PAR1",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
    }
    if extension in signatures and not any(
        content.startswith(signature) for signature in signatures[extension]
    ):
        reasons.append("SIGNATURE_MISMATCH")
    if extension in {".png", ".jpg", ".jpeg"} and not any(
        reason == "SIGNATURE_MISMATCH" for reason in reasons
    ):
        try:
            from PIL import Image

            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 100_000_000:
                    reasons.append("PIXEL_LIMIT_EXCEEDED")
        except (OSError, ValueError):
            reasons.append("IMAGE_INVALID")
    status = (
        DocumentQualityStatus.REJECTED if reasons else DocumentQualityStatus.ACCEPTED
    )
    return DocumentPreflightResult(
        status,
        tuple(reasons),
        extension,
        mime_type,
        len(content) if isinstance(content, bytes) else 0,
    )


__all__ = ["preflight_document"]
