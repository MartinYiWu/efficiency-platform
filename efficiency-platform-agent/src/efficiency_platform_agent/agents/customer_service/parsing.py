"""智能客服知识文档的本地解析适配器。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any


class CustomerServiceDocumentParser:
    def __init__(self, docling_parser: Any) -> None:
        self.docling_parser = docling_parser

    def parse(self, content: bytes, filename: str) -> dict[str, str]:
        suffix = Path(filename).suffix.lower()
        if suffix in {".txt", ".md"}:
            return {"text": content.decode("utf-8-sig")}
        if suffix in {".html", ".htm"}:
            import trafilatura

            text = trafilatura.extract(content.decode("utf-8", errors="replace"))
            return {"text": text or ""}
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            return {
                "text": "\n\n".join(page.extract_text() or "" for page in reader.pages)
            }
        return self.docling_parser.parse(content, filename)


__all__ = ["CustomerServiceDocumentParser"]
