"""智能客服知识文档的本地解析适配器。"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any


class CustomerServiceDocumentParser:
    def __init__(self, docling_parser: Any) -> None:
        self.docling_parser = docling_parser

    def parse(self, content: bytes, filename: str) -> dict[str, Any]:
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
            return join_pages(tuple(page.extract_text() or "" for page in reader.pages))
        return self.docling_parser.parse(content, filename)


def join_pages(pages: tuple[str, ...]) -> dict[str, Any]:
    texts: list[str] = []
    markers: list[tuple[int, int]] = []
    offset = 0
    for page_no, page in enumerate(pages, 1):
        page = page.replace("\r\n", "\n").replace("\r", "\n")
        if not page.strip():
            continue
        if texts:
            offset += 2
        markers.append((offset, page_no))
        texts.append(page)
        offset += len(page)
    return {"text": "\n\n".join(texts), "page_markers": tuple(markers)}


__all__ = ["CustomerServiceDocumentParser", "join_pages"]
