"""本地简历读取、身份隔离和可逆定位；不联网下载依赖。"""

import hashlib
import io
import re
import zipfile
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree

from efficiency_platform_agent.contracts.hr import (
    Block,
    Evidence,
    ExtractionOutput,
    Identity,
    IdentityValue,
    Offset,
)

from .local_tools import LocalToolDependencies, convert_doc, unpack_archive


class TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.elements: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = re.sub(r"\s+", "", attributes.get("style") or "").lower()
        hidden = (
            bool(self.elements and self.elements[-1][1])
            or tag in ("script", "style", "template", "noscript")
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if tag not in (
            "br",
            "img",
            "input",
            "meta",
            "link",
            "hr",
            "wbr",
            "source",
            "area",
            "base",
            "embed",
            "param",
            "track",
            "col",
        ):
            self.elements.append((tag, hidden))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.elements) - 1, -1, -1):
            if self.elements[index][0] == tag:
                del self.elements[index:]
                break

    def handle_data(self, data: str) -> None:
        if not self.elements or not self.elements[-1][1]:
            self.parts.append(data)


def dependency_readiness(
    ocr: Callable[[bytes], list[Block]] | None = None,
) -> dict[str, str]:
    import importlib.util

    tools = LocalToolDependencies.detect()
    return {
        "txt": "available",
        "md": "available",
        "html": "available",
        "docx": "available",
        "pdf": "available" if importlib.util.find_spec("pypdf") else "unavailable",
        "image": "available" if ocr else "unavailable",
        "doc": "available" if tools.libreoffice else "unavailable",
        "zip": "available",
        "rar": "available" if tools.seven_zip else "unavailable",
        "7z": "available" if tools.seven_zip else "unavailable",
    }


def _read_blocks(
    filename: str, content: bytes, ocr: Callable[[bytes], list[Block]] | None
) -> list[Block]:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".doc":
        return _read_blocks("converted.docx", convert_doc(content), ocr)
    if suffix in (".txt", ".md", ".html", ".htm"):
        if (
            content.startswith(
                (
                    b"%PDF-",
                    b"PK\x03\x04",
                    b"\xd0\xcf\x11\xe0",
                    b"\x89PNG",
                    b"\xff\xd8\xff",
                )
            )
            or b"\x00" in content
            and not content.startswith((b"\xff\xfe", b"\xfe\xff"))
        ):
            raise ValueError("HR_FILE_MAGIC_INVALID")
        try:
            text = content.decode(
                "utf-16"
                if content.startswith((b"\xff\xfe", b"\xfe\xff"))
                else "utf-8-sig"
            )
        except UnicodeDecodeError as e:
            from charset_normalizer import from_bytes

            detected = from_bytes(content).best()
            if detected is None or detected.chaos > 0.10:
                raise ValueError("HR_FILE_ENCODING_UNSUPPORTED") from e
            text = str(detected)
        if "\x00" in text:
            raise ValueError("HR_FILE_MAGIC_INVALID")
        if suffix in (".html", ".htm"):
            parser = TextHTMLParser()
            parser.feed(text)
            text = "\n".join(parser.parts)
        return [
            Block(block_id=f"p{i + 1}", text=line, paragraph=i + 1)
            for i, line in enumerate(text.splitlines())
            if line.strip()
        ]
    if suffix == ".docx":
        if not content.startswith(b"PK"):
            raise ValueError("HR_FILE_MAGIC_INVALID")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if (
                sum(x.file_size for x in members) > 100 * 1024 * 1024
                or len(members) > 10000
            ):
                raise ValueError("HR_FILE_ARCHIVE_LIMIT")
            xml = archive.read("word/document.xml")
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise ValueError("HR_FILE_XML_UNSAFE")
        root = ElementTree.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        return [
            Block(
                block_id=f"p{i + 1}",
                text="".join(
                    t.text or ""
                    for run in p.iter(ns + "r")
                    if run.find(ns + "rPr/" + ns + "vanish") is None
                    for t in run.iter(ns + "t")
                ),
                paragraph=i + 1,
            )
            for i, p in enumerate(root.iter(ns + "p"))
        ]
    if suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("HR_FILE_MAGIC_INVALID")
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("HR_FILE_PDF_LIMIT")
        blocks = [
            Block(block_id=f"page{i + 1}", text=p.extract_text() or "", page=i + 1)
            for i, p in enumerate(reader.pages)
        ]
        if any(not b.text.strip() for b in blocks):
            if ocr is None:
                raise ValueError("FORMAT_SERVICE_UNAVAILABLE:OCR")
            return ocr(content)
        return blocks
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 40000000:
                raise ValueError("HR_FILE_IMAGE_LIMIT")
            image.verify()
        if ocr is None:
            raise ValueError("FORMAT_SERVICE_UNAVAILABLE:OCR")
        return ocr(content)
    raise ValueError("FORMAT_SERVICE_UNAVAILABLE")


PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NAME = re.compile(
    r"^[ \t]*(?:姓名|Name)[ \t]*[:：][ \t]*([A-Za-z][A-Za-z'.-]*(?:[ \t]+[A-Za-z][A-Za-z'.-]*)*|[^\s,，;；]{2,30})",
    re.IGNORECASE | re.MULTILINE,
)
SENSITIVE_LINE = re.compile(
    r"(?:性别|年龄|出生|生日|民族|婚姻|婚育|生育|籍贯|政治面貌|宗教|身份证|银行卡|社保号|户籍|健康状况|残疾|性取向|血型|星座|身高|体重|\b(?:gender|sex|age|date of birth|birth date|marital status|ethnicity|race|religion|blood type|zodiac|height|weight|political affiliation|health status))\s*[:：].*",
    re.IGNORECASE,
)


def private_number_spans(text: str) -> list[tuple[int, int]]:
    """证件与银行卡仅在CPU校验后隔离，值不进入身份结构或模型。"""
    spans = []
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    for item in re.finditer(r"(?<![0-9])[0-9]{17}[0-9Xx](?![0-9])", text):
        value = item.group()
        if (
            "10X98765432"[
                sum(int(n) * w for n, w in zip(value[:17], weights, strict=True)) % 11
            ]
            == value[-1].upper()
        ):
            spans.append(item.span())
    for item in re.finditer(r"(?<![0-9])[0-9]{16,19}(?![0-9])", text):
        total = 0
        for index, char in enumerate(reversed(item.group())):
            number = int(char) * (2 if index % 2 else 1)
            total += number - 9 if number > 9 else number
        if total % 10 == 0:
            spans.append(item.span())
    return spans


def extract_resume(
    filename: str,
    content: bytes,
    expected_hash: str,
    *,
    ocr: Callable[[bytes], list[Block]] | None = None,
) -> ExtractionOutput:
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_hash:
        raise ValueError("HR_FILE_HASH_MISMATCH")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("HR_FILE_SIZE_LIMIT")
    blocks = _read_blocks(filename, content, ocr)
    if sum(len(b.text) for b in blocks) > 100000:
        raise ValueError("HR_FILE_TEXT_LIMIT")
    names: list[IdentityValue] = []
    phones: list[IdentityValue] = []
    emails: list[IdentityValue] = []
    spans: dict[str, list[tuple[int, int]]] = {}
    for block in blocks:
        local: list[tuple[int, int]] = []
        for pattern, target, group in (
            (NAME, names, 1),
            (PHONE, phones, 0),
            (EMAIL, emails, 0),
        ):
            for match in pattern.finditer(block.text):
                start, end = match.span(group)
                target.append(
                    IdentityValue(
                        value=match.group(group),
                        quality=100,
                        evidence=[
                            Evidence(
                                block_id=block.block_id,
                                start=start,
                                end=end,
                                quote=match.group(group),
                            )
                        ],
                    )
                )
                local.append((start, end))
        local.extend(m.span() for m in SENSITIVE_LINE.finditer(block.text))
        local.extend(private_number_spans(block.text))
        spans[block.block_id] = local
    distinct = {n.value for n in names}
    name = names[0] if len(distinct) == 1 else IdentityValue(conflict=len(distinct) > 1)
    if not names and blocks:
        first = blocks[0]
        if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", first.text.strip()):
            start = first.text.index(first.text.strip())
            name = IdentityValue(
                value=first.text.strip(),
                quality=60,
                evidence=[
                    Evidence(
                        block_id=first.block_id,
                        start=start,
                        end=start + len(first.text.strip()),
                        quote=first.text.strip(),
                    )
                ],
            )
            spans[first.block_id].append((start, start + len(first.text.strip())))
    # 所有已定位身份值的重复出现也必须清除，不能仅清洗首个标注位置。
    values = {x.value for x in names + phones + emails + [name] if x.value}
    cleaned: list[Block] = []
    for block in blocks:
        removed = [False] * len(block.text)
        for value in values:
            assert value is not None
            for match in re.finditer(re.escape(value), block.text):
                spans[block.block_id].append(match.span())
        for start, end in spans[block.block_id]:
            removed[start:end] = [True] * (end - start)
        text = ""
        offsets: list[Offset] = []
        index = 0
        while index < len(block.text):
            if removed[index]:
                index += 1
                continue
            end = index + 1
            while end < len(block.text) and not removed[end]:
                end += 1
            offsets.append(
                Offset(
                    clean_start=len(text),
                    clean_end=len(text) + end - index,
                    source_start=index,
                    source_end=end,
                )
            )
            text += block.text[index:end]
            index = end
        cleaned.append(block.model_copy(update={"text": text, "offsets": offsets}))
    for collection in (phones, emails):
        if len({x.value for x in collection}) > 1:
            collection[:] = [
                x.model_copy(update={"conflict": True}) for x in collection
            ]
    source_blocks = []
    for block in blocks:
        chars = list(block.text)
        for start, end in private_number_spans(block.text):
            chars[start:end] = ["*"] * (end - start)
        source_blocks.append(block.model_copy(update={"text": "".join(chars)}))
    return ExtractionOutput(
        blocks=source_blocks,
        cleaned_blocks=cleaned,
        identity=Identity(
            name=name,
            phones=phones,
            emails=emails,
            confirmation_required=name.quality < 100,
        ),
        content_hash=digest,
    )


def model_safe_blocks(blocks: list[Block]) -> list[Block]:
    names = {m.group(1) for b in blocks for m in NAME.finditer(b.text)}
    clean: list[Block] = []
    for block in blocks:
        text = block.text
        spans = [
            m.span() for p in (PHONE, EMAIL, SENSITIVE_LINE) for m in p.finditer(text)
        ]
        spans.extend(private_number_spans(text))
        spans.extend(m.span(1) for m in NAME.finditer(text))
        for name in names:
            spans.extend(m.span() for m in re.finditer(re.escape(name), text))
        chars = list(text)
        for start, end in spans:
            chars[start:end] = [" "] * (end - start)
        clean.append(block.model_copy(update={"text": "".join(chars)}))
    return clean


def extract_archive_raw(
    content: bytes, expected_hash: str, *, extension: str = ".zip"
) -> list[dict[str, object]]:
    """原件出口先完成整包安全校验，返回有限原件供Java原子登记；不调用模型。"""
    import base64

    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("HR_FILE_HASH_MISMATCH")
    if not content or len(content) > 100 * 1024 * 1024:
        raise ValueError("HR_FILE_ARCHIVE_SIZE_LIMIT")
    if extension in (".rar", ".7z"):
        files = unpack_archive(content, extension)
    elif extension == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = [item for item in archive.infolist() if not item.is_dir()]
                if (
                    not entries
                    or len(entries) > 100
                    or sum(item.file_size for item in entries) > 500 * 1024 * 1024
                ):
                    raise ValueError("HR_FILE_ARCHIVE_LIMIT")
                seen: set[str] = set()
                for item in entries:
                    name = item.filename.replace("\\", "/")
                    path = PurePosixPath(name)
                    if (
                        not name
                        or path.is_absolute()
                        or ".." in path.parts
                        or len(path.parts) > 8
                        or ":" in name
                        or name.casefold() in seen
                        or (item.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ValueError("HR_FILE_ARCHIVE_PATH_INVALID")
                    seen.add(name.casefold())
                    if path.suffix.casefold() in (
                        ".zip",
                        ".rar",
                        ".7z",
                        ".tar",
                        ".gz",
                        ".bz2",
                        ".xz",
                    ):
                        raise ValueError("HR_FILE_ARCHIVE_NESTED")
                    if (
                        item.flag_bits & 1
                        or item.file_size < 1
                        or item.file_size > 20 * 1024 * 1024
                        or item.file_size > max(1, item.compress_size) * 100
                    ):
                        raise ValueError("HR_FILE_ARCHIVE_LIMIT")
                files = [(item.filename, archive.read(item)) for item in entries]
        except zipfile.BadZipFile as error:
            raise ValueError("HR_FILE_ARCHIVE_INVALID") from error
    else:
        raise ValueError("HR_FILE_ARCHIVE_INVALID")
    if (
        not files
        or len(files) > 100
        or sum(len(raw) for _, raw in files) > 500 * 1024 * 1024
    ):
        raise ValueError("HR_FILE_ARCHIVE_LIMIT")
    allowed = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt", ".md", ".html"}
    for name, raw in files:
        if (
            PurePosixPath(name).suffix.casefold() not in allowed
            or not raw
            or len(raw) > 20 * 1024 * 1024
        ):
            raise ValueError("HR_FILE_ARCHIVE_DOCUMENT_INVALID")
    return [
        {
            "filename": name,
            "content_base64": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        for name, raw in files
    ]


def extract_archive(
    content: bytes,
    expected_hash: str,
    *,
    ocr: Callable[[bytes], list[Block]] | None = None,
    extension: str = ".zip",
) -> list[dict[str, object]]:
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError("HR_FILE_HASH_MISMATCH")
    if len(content) > 100 * 1024 * 1024:
        raise ValueError("HR_FILE_ARCHIVE_SIZE_LIMIT")
    if extension in (".rar", ".7z"):
        files = unpack_archive(content, extension)
        converted: list[dict[str, object]] = []
        for filename, raw in files:
            try:
                extracted = extract_resume(
                    filename, raw, hashlib.sha256(raw).hexdigest(), ocr=ocr
                )
                converted.append(
                    {
                        "filename": filename,
                        "status": "EXTRACTED",
                        "data": extracted.model_dump(mode="json"),
                    }
                )
            except (ValueError, ImportError) as error:
                code = str(error).split(":")[0]
                converted.append(
                    {
                        "filename": filename,
                        "status": "FAILED",
                        "code": code
                        if code.startswith(("HR_FILE_", "FORMAT_"))
                        else "HR_FILE_ITEM_UNREADABLE",
                    }
                )
        return converted
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = [item for item in archive.infolist() if not item.is_dir()]
            if (
                len(entries) > 100
                or sum(x.file_size for x in entries) > 500 * 1024 * 1024
            ):
                raise ValueError("HR_FILE_ARCHIVE_LIMIT")
            names: set[str] = set()
            for item in entries:
                name = item.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or len(path.parts) > 8
                    or ".." in path.parts
                    or ":" in name
                    or name.casefold() in names
                    or (item.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("HR_FILE_ARCHIVE_PATH_INVALID")
                names.add(name.casefold())
                if path.suffix.casefold() in (
                    ".zip",
                    ".rar",
                    ".7z",
                    ".gz",
                    ".tar",
                    ".bz2",
                    ".xz",
                ):
                    raise ValueError("HR_FILE_ARCHIVE_NESTED")
                if (
                    item.file_size > 20 * 1024 * 1024
                    or item.file_size > max(1, item.compress_size) * 100
                    or item.flag_bits & 1
                ):
                    raise ValueError("HR_FILE_ARCHIVE_LIMIT")
            results: list[dict[str, object]] = []
            for item in entries:
                data = archive.read(item)
                try:
                    result = extract_resume(
                        item.filename, data, hashlib.sha256(data).hexdigest(), ocr=ocr
                    )
                    results.append(
                        {
                            "filename": item.filename,
                            "status": "EXTRACTED",
                            "data": result.model_dump(mode="json"),
                        }
                    )
                except (ValueError, ImportError) as error:
                    code = str(error).split(":")[0]
                    if not code.startswith(("HR_FILE_", "FORMAT_SERVICE_")):
                        code = "HR_FILE_ITEM_UNREADABLE"
                    results.append(
                        {
                            "filename": item.filename,
                            "status": "FAILED",
                            "code": code,
                        }
                    )
            return results
    except zipfile.BadZipFile as error:
        raise ValueError("HR_FILE_ARCHIVE_INVALID") from error
