"""Docling 解析器注入边界；默认不加载模型。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any


class DoclingParser:
    """将解析器作为依赖注入，避免模块导入时下载或初始化模型。"""

    def __init__(self, parser: Any = None, converter_factory: Any = None) -> None:
        self.parser = parser
        self.converter_factory = converter_factory

    def parse(self, content: bytes, filename: str) -> Any:
        """把字节内容交给注入解析器，或使用延迟加载的 Docling。"""
        if self.parser is None:
            return self._parse_with_docling(content, filename)
        return self.parser(content, filename)

    def _parse_with_docling(self, content: bytes, filename: str) -> dict[str, str]:
        """通过临时文件调用 Docling，并只返回可序列化的 Markdown AST。"""
        if not isinstance(content, bytes) or not content:
            raise ValueError("DOCLING_CONTENT_INVALID")
        suffix = Path(filename).suffix.lower() or ".txt"
        if suffix == ".pdf" and self.converter_factory is None:
            # PDF 管线会初始化布局模型；没有显式本地管线时必须失败关闭，避免隐式下载。
            raise RuntimeError("DOCLING_PDF_PIPELINE_REQUIRED")
        factory = self.converter_factory
        if factory is None:
            from docling.document_converter import DocumentConverter

            factory = DocumentConverter

        converter = factory()
        with tempfile.TemporaryDirectory(prefix="agent-docling-") as folder:
            source = Path(folder) / f"source{suffix}"
            source.write_bytes(content)
            result = converter.convert(source, raises_on_error=True)
        document = getattr(result, "document", None)
        export = getattr(document, "export_to_markdown", None)
        if not callable(export):
            raise TypeError("DOCLING_RESULT_INVALID")
        markdown = export()
        if not isinstance(markdown, str):
            raise TypeError("DOCLING_RESULT_INVALID")
        return {"kind": "docling_markdown", "text": markdown}


__all__ = ["DoclingParser"]
