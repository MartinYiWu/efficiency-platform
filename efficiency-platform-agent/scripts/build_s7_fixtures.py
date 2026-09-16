"""生成 S7 离线固定样本；只写入显式指定的输出目录。"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import io
import json
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FixtureValue = str | bytes

_FIXTURES: dict[str, tuple[str, int, FixtureValue]] = {
    "plain_text_v1.md": ("text", 1, "青禾实验室\nS7 固定文本样本。\n"),
    "structured_document_v1.docx": ("document", 1, b"S7-DOCX-FIXTURE"),
    "table_document_v1.xlsx": ("spreadsheet", 1, b"S7-XLSX-FIXTURE"),
    "text_pdf_v1.pdf": ("pdf_text", 1, b"S7-PDF-TEXT-FIXTURE"),
    "scan_pdf_v1.pdf": ("pdf_scan", 1, b"S7-PDF-SCAN-FIXTURE"),
    "mixed_pdf_v1.pdf": ("pdf_mixed", 2, b"S7-PDF-MIXED-FIXTURE"),
    "ocr_zh_en_v1.png": ("image", 1, b"S7-OCR-ZH-EN-FIXTURE"),
    "analytics_metrics_v1.csv": (
        "analytics",
        1,
        "date,channel,visits,activations\n2026-01-01,web,10,2\n",
    ),
    "analytics_metrics_v1.json": (
        "analytics",
        1,
        '[{"date":"2026-01-01","channel":"web","visits":10,"activations":2}]',
    ),
    "analytics_metrics_v1.parquet": ("analytics", 1, b"S7-PARQUET-FIXTURE"),
    "analytics_metrics_v1.xlsx": ("analytics", 1, b"S7-ANALYTICS-XLSX-FIXTURE"),
    "rejected_signature_mismatch_v1.png": ("rejected", 1, b"S7-REJECTED-SIGNATURE"),
}


def _zip_payload(files: dict[str, str]) -> bytes:
    """生成时间戳固定的 ZIP 容器，保证样本可重复。"""
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, content.encode("utf-8"))
    return buffer.getvalue()


def _docx_payload() -> bytes:
    """生成包含一段固定中文文本的最小 DOCX。"""
    return _zip_payload(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                "</Relationships>"
            ),
            "word/document.xml": (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>青禾实验室固定文档</w:t></w:r></w:p>"
                "<w:sectPr/></w:body></w:document>"
            ),
        }
    )


def _xlsx_payload() -> bytes:
    """生成包含固定表头和一行数据的最小 XLSX。"""
    return _zip_payload(
        {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                "</Types>"
            ),
            "_rels/.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                "</Relationships>"
            ),
            "xl/workbook.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
            "xl/worksheets/sheet1.xml": (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>date</t></is></c><c r="B1" t="inlineStr"><is><t>channel</t></is></c><c r="C1" t="inlineStr"><is><t>visits</t></is></c><c r="D1" t="inlineStr"><is><t>activations</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>2026-01-01</t></is></c><c r="B2" t="inlineStr"><is><t>web</t></is></c><c r="C2"><v>10</v></c><c r="D2"><v>2</v></c></row>'
                "</sheetData></worksheet>"
            ),
        }
    )


def _pdf_payload(page_texts: tuple[str, ...]) -> bytes:
    """生成带固定文本页的最小 PDF，避免依赖外部转换器。"""
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_ids = [3 + index * 2 for index in range(len(page_texts))]
    kids = " ".join(f"{item} 0 R" for item in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for index, text in enumerate(page_texts):
        page_id = page_ids[index]
        content_id = page_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 16 Tf 30 150 Td ({escaped}) Tj ET".encode("ascii")
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    output.extend(
        "".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode()
    )
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _png_payload() -> bytes:
    """生成确定性的 1x1 RGB PNG。"""
    raw = b"\x00\xff\xff\xff"

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )


def _fixture_payload(name: str, value: str | bytes) -> bytes:
    """按样本类型生成可被对应解析器识别的文件内容。"""
    if name == "structured_document_v1.docx":
        return _docx_payload()
    if name in {"table_document_v1.xlsx", "analytics_metrics_v1.xlsx"}:
        return _xlsx_payload()
    if name == "text_pdf_v1.pdf":
        return _pdf_payload(("Qinghe Laboratory report",))
    if name == "scan_pdf_v1.pdf":
        return _pdf_payload(("Qinghe Laboratory scan",))
    if name == "mixed_pdf_v1.pdf":
        return _pdf_payload(
            ("Qinghe Laboratory page one", "Qinghe Laboratory page two")
        )
    if name == "rejected_signature_mismatch_v1.png":
        return b"not-a-valid-png-signature"
    if name == "ocr_zh_en_v1.png":
        return _png_payload()
    if name == "analytics_metrics_v1.parquet":
        import polars as pl

        buffer = io.BytesIO()
        pl.DataFrame(
            {
                "date": ["2026-01-01"],
                "channel": ["web"],
                "visits": [10],
                "activations": [2],
            }
        ).write_parquet(buffer)
        return buffer.getvalue()
    return value.encode("utf-8") if isinstance(value, str) else value


def build(output: Path, seed: str) -> dict[str, object]:
    """按固定 seed 生成合成文件和 manifest。"""
    if not seed.strip():
        raise ValueError("seed不能为空")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for name, (kind, pages, value) in _FIXTURES.items():
        payload = _fixture_payload(name, value)
        target = output / name
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        expected_structure: object = {
            "analytics": ["date", "channel", "visits", "activations"],
            "document": "docling_markdown",
            "spreadsheet": ["date", "channel", "visits", "activations"],
            "pdf_text": "docling_markdown",
            "pdf_scan": "ocr_required",
            "pdf_mixed": "page_level_document",
            "image": "ocr_required",
            "rejected": "rejected_before_parse",
            "text": "docling_markdown",
        }[kind]
        entries.append(
            {
                "name": name,
                "kind": kind,
                "pages": pages,
                "sha256": digest,
                "subject": "青禾实验室",
                "expected_structure": expected_structure,
                "generator_version": "s7-fixtures/1",
            }
        )
    manifest: dict[str, object] = {
        "manifest_version": "s7-fixture-manifest/1",
        "seed": seed,
        "generator_version": "s7-fixtures/1",
        "fixtures": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 S7 离线固定样本")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", default="s7-fixed")
    args = parser.parse_args()
    build(args.output, args.seed)


if __name__ == "__main__":
    main()
