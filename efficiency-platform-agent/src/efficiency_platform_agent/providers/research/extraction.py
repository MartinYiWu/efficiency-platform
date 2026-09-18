"""对已下载内容执行离线、受限的正文抽取。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any

from charset_normalizer import from_bytes

from efficiency_platform_agent.contracts.research_sources_v2 import (
    ExtractedDocumentV2,
    FetchedContentV2,
)

from ._process_isolation import (
    IsolatedParseFailed,
    IsolatedParseTimeout,
    run_isolated_parser,
)
from ._xml_safety import UnsafeXmlError, parse_safe_xml


class DocumentExtractionError(RuntimeError):
    def __init__(self, code: str, reason_code: str) -> None:
        if code not in {
            "CONTENT_REJECTED",
            "CONTENT_UNAVAILABLE",
            "SOURCE_SCHEMA_INVALID",
        }:
            raise ValueError("DOCUMENT_EXTRACTION_ERROR_INVALID")
        super().__init__(code)
        self.code = code
        self.reason_code = reason_code


class DocumentExtractor:
    version = "research-extractor/2.0"

    def __init__(
        self,
        *,
        html_extractor: Callable[[str], str | None] | None = None,
        allow_in_process_test_parser: bool = False,
        parse_timeout_seconds: float = 3.0,
        max_body_bytes: int = 2 * 1024 * 1024,
        max_xml_depth: int = 32,
        max_xml_nodes: int = 20_000,
    ) -> None:
        if html_extractor is not None and not allow_in_process_test_parser:
            raise ValueError("IN_PROCESS_TEST_PARSER_NOT_ALLOWED")
        if parse_timeout_seconds <= 0:
            raise ValueError("PARSE_TIMEOUT_INVALID")
        self.html_extractor = html_extractor
        self.parse_timeout_seconds = parse_timeout_seconds
        self.max_body_bytes = max_body_bytes
        self.max_xml_depth = max_xml_depth
        self.max_xml_nodes = max_xml_nodes

    def extract(self, content: FetchedContentV2) -> ExtractedDocumentV2:
        if len(content.body) > self.max_body_bytes:
            raise DocumentExtractionError("CONTENT_REJECTED", "DOCUMENT_TOO_LARGE")
        media_type = content.media_type.split(";", 1)[0].strip().lower()
        if media_type == "text/html":
            source = _decode(content.body)
            title = _html_title(source)
            try:
                if self.html_extractor is None:
                    result = run_isolated_parser(
                        "html",
                        source,
                        timeout_seconds=self.parse_timeout_seconds,
                    )
                    text = result if isinstance(result, str) else ""
                else:
                    text = self.html_extractor(source) or ""
            except IsolatedParseTimeout as exc:
                raise DocumentExtractionError(
                    "CONTENT_UNAVAILABLE", "HTML_EXTRACTION_TIMEOUT"
                ) from exc
            except IsolatedParseFailed as exc:
                raise DocumentExtractionError(
                    "CONTENT_UNAVAILABLE", "HTML_EXTRACTION_FAILED"
                ) from exc
            except Exception as exc:
                raise DocumentExtractionError(
                    "CONTENT_UNAVAILABLE", "HTML_EXTRACTION_FAILED"
                ) from exc
        elif media_type == "text/plain":
            text = _decode(content.body).strip()
            title = _first_line(text)
        elif media_type == "application/json" or media_type.endswith("+json"):
            title, text = _extract_json(content.body)
        elif media_type in {
            "application/xml",
            "application/rss+xml",
            "application/atom+xml",
            "text/xml",
        } or media_type.endswith("+xml"):
            title, text = self._extract_xml(content.body)
        else:
            raise DocumentExtractionError(
                "CONTENT_REJECTED", "DOCUMENT_MEDIA_TYPE_FORBIDDEN"
            )
        text = text.strip()
        if not text:
            raise DocumentExtractionError("CONTENT_UNAVAILABLE", "DOCUMENT_EMPTY")
        title = (title.strip() or _first_line(text) or "Untitled document")[:2000]
        return ExtractedDocumentV2(
            candidate_id=content.candidate_id,
            canonical_url=content.final_url,
            title=title,
            text=text,
            content_hash=hashlib.sha256(content.body).hexdigest(),
            published_at=None,
            extractor_version=self.version,
        )

    def _extract_xml(self, body: bytes) -> tuple[str, str]:
        try:
            root = parse_safe_xml(
                body,
                max_depth=self.max_xml_depth,
                max_nodes=self.max_xml_nodes,
            )
        except UnsafeXmlError as exc:
            code = "SOURCE_SCHEMA_INVALID" if str(exc) == "XML_INVALID" else "CONTENT_REJECTED"
            raise DocumentExtractionError(code, str(exc)) from exc
        pieces = [part.strip() for part in root.itertext() if part.strip()]
        title = next(
            (
                (element.text or "").strip()
                for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].lower() == "title"
                and (element.text or "").strip()
            ),
            "",
        )
        return title, "\n".join(pieces)


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.parts.append(data)


def _html_title(value: str) -> str:
    parser = _TitleParser()
    parser.feed(value)
    return " ".join(part.strip() for part in parser.parts if part.strip())


def _decode(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        best = from_bytes(value).best()
        if best is None:
            raise DocumentExtractionError(
                "SOURCE_SCHEMA_INVALID", "DOCUMENT_ENCODING_UNKNOWN"
            )
        return str(best)


def _extract_json(body: bytes) -> tuple[str, str]:
    try:
        value: Any = json.loads(_decode(body))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DocumentExtractionError("SOURCE_SCHEMA_INVALID", "JSON_INVALID") from exc
    title = value.get("title", "") if isinstance(value, dict) else ""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(title), text


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")


__all__ = ["DocumentExtractionError", "DocumentExtractor"]
