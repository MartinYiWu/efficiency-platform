import hashlib

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.hr.evaluation import (
    semantic_batches,
    validate_assessments,
)
from efficiency_platform_agent.agents.hr.extraction import extract_resume
from efficiency_platform_agent.agents.hr.interview import interview_plan
from efficiency_platform_agent.contracts.hr import Assessment, Evidence, HrSkillRequest


def test_unknown_zero_evidence_and_known_requires_evidence():
    Assessment(requirement_id="a", status="UNKNOWN", reason="缺证据", evidence=[])
    with pytest.raises(ValidationError):
        Assessment(requirement_id="a", status="MATCH", reason="符合", evidence=[])
    with pytest.raises(ValidationError):
        Assessment(
            requirement_id="a", status="NOT_APPLICABLE", reason="无关", evidence=[]
        )


def test_extract_identity_redaction_and_offset_mapping():
    content = "姓名：张三\n手机：13812345678\n邮箱：zhang@example.com\nPython开发五年".encode()
    result = extract_resume("resume.txt", content, hashlib.sha256(content).hexdigest())
    assert result.identity.name.value == "张三"
    assert result.identity.name.quality == 100
    clean = "\n".join(b.text for b in result.cleaned_blocks)
    assert all(s not in clean for s in ("张三", "13812345678", "zhang@example.com"))
    assert "Python开发五年" in clean
    for block in result.cleaned_blocks:
        for mapping in block.offsets:
            original = next(b for b in result.blocks if b.block_id == block.block_id)
            assert (
                block.text[mapping.clean_start : mapping.clean_end]
                == original.text[mapping.source_start : mapping.source_end]
            )


def test_bad_hash_and_unsupported_format_fail_closed():
    with pytest.raises(ValueError, match="HR_FILE_HASH"):
        extract_resume("r.txt", b"hello", "0" * 64)
    with pytest.raises(ValueError, match="FORMAT_SERVICE_UNAVAILABLE"):
        extract_resume("r.exe", b"hello", hashlib.sha256(b"hello").hexdigest())


def test_evidence_exact_offsets_and_cover_once():
    request = HrSkillRequest(
        run_id="r",
        operation_id="op",
        candidate_ref="c",
        blocks=[{"block_id": "b", "text": "Python经验"}],
        requirements=[{"requirement_id": "a", "criterion": "Python"}],
    )
    valid = Assessment(
        requirement_id="a",
        status="MATCH",
        reason="有证据",
        evidence=[Evidence(block_id="b", start=0, end=6, quote="Python")],
    )
    validate_assessments(request.requirements, [valid], request.blocks)
    with pytest.raises(ValueError, match="HR_FACT_EVIDENCE"):
        validate_assessments(
            request.requirements,
            [
                valid.model_copy(
                    update={
                        "evidence": [
                            Evidence(block_id="b", start=1, end=7, quote="Python")
                        ]
                    }
                )
            ],
            request.blocks,
        )
    with pytest.raises(ValueError, match="HR_EVALUATION_COVERAGE"):
        validate_assessments(request.requirements, [], request.blocks)


def test_shared_semantic_limit_and_dedup():
    reqs = [{"requirement_id": str(i), "criterion": f"技能{i}"} for i in range(60)]
    assert [len(b) for b in semantic_batches(reqs)] == [15] * 4
    with pytest.raises(ValueError, match="WORK_LIMIT"):
        semantic_batches(reqs + [{"requirement_id": "60", "criterion": "额外"}])


def test_interview_presets_and_overrun():
    assert interview_plan(60) == ((4, 3, 2, 4, 3, 1), (3, 3, 3, 4, 4, 3))
    with pytest.raises(ValueError, match="HR_INTERVIEW_DURATION"):
        interview_plan(30, (10, 10, 10, 10, 0, 0))


def test_zip_extract_checks_traversal_nested_and_bomb_before_reading():
    import io
    import zipfile

    from efficiency_platform_agent.agents.hr.extraction import extract_archive

    def archive(name, content):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr(name, content)
        return stream.getvalue()

    for name in ("../a.txt", "a.zip", "/etc/a.txt", "C:/a.txt"):
        content = archive(name, b"a")
        with pytest.raises(ValueError, match="HR_FILE_ARCHIVE"):
            extract_archive(content, hashlib.sha256(content).hexdigest())
    content = archive("a.txt", "Python工程师".encode())
    result = extract_archive(content, hashlib.sha256(content).hexdigest())
    assert len(result) == 1 and result[0]["filename"] == "a.txt"


def test_date_precision_preserves_year_and_month_and_rejects_invented_day():
    from efficiency_platform_agent.contracts.hr import DateValue

    assert (
        DateValue(value="2024", precision="YEAR", source_text="2024年").value == "2024"
    )
    assert (
        DateValue(value="2024-03", precision="MONTH", source_text="2024年3月").precision
        == "MONTH"
    )
    with pytest.raises(ValidationError):
        DateValue(value="2024-03-01", precision="MONTH", source_text="2024年3月")


def test_docx_html_and_image_local_readers_with_explicit_ocr_boundary():
    import io
    import zipfile

    from PIL import Image

    from efficiency_platform_agent.contracts.hr import Block

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Python开发</w:t></w:r></w:p></w:body></w:document>',
        )
    content = stream.getvalue()
    parsed = extract_resume("r.docx", content, hashlib.sha256(content).hexdigest())
    assert parsed.blocks[0].text == "Python开发"
    content = b"<html><script>send secrets</script><p>Python</p></html>"
    parsed = extract_resume("r.html", content, hashlib.sha256(content).hexdigest())
    assert "send secrets" not in str(parsed.blocks)
    image = io.BytesIO()
    Image.new("RGB", (10, 10)).save(image, format="PNG")
    content = image.getvalue()
    with pytest.raises(ValueError, match="FORMAT_SERVICE_UNAVAILABLE"):
        extract_resume("r.png", content, hashlib.sha256(content).hexdigest())
    parsed = extract_resume(
        "r.png",
        content,
        hashlib.sha256(content).hexdigest(),
        ocr=lambda _: [Block(block_id="ocr1", text="Python", page=1)],
    )
    assert parsed.blocks[0].text == "Python"


def test_pdf_scanned_pages_do_not_silently_omit_ocr():
    import io

    from pypdf import PdfWriter

    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(stream)
    content = stream.getvalue()
    with pytest.raises(ValueError, match="FORMAT_SERVICE_UNAVAILABLE"):
        extract_resume("r.pdf", content, hashlib.sha256(content).hexdigest())


def test_large_single_unicode_block_splits_without_loss_and_maps_offsets():
    from efficiency_platform_agent.agents.hr.facts import split_fact_blocks
    from efficiency_platform_agent.contracts.hr import Block

    text = "项目Python开发。" * 9000
    chunks, mapping = split_fact_blocks([Block(block_id="original", text=text)])
    assert 1 < len(chunks) <= 12
    pieces = [b for chunk in chunks for b in chunk]
    assert "".join(b.text for b in pieces) == text
    for block in pieces:
        source, start = mapping[block.block_id]
        assert source == "original"
        assert text[start : start + len(block.text)] == block.text
        assert len(block.model_dump_json().encode()) <= 36 * 1024


def test_local_dependency_adapters_fail_closed_or_use_bounded_argument_commands(
    tmp_path,
):
    from efficiency_platform_agent.agents.hr.local_tools import (
        LocalToolDependencies,
        convert_doc,
    )

    dependencies = LocalToolDependencies(libreoffice=None, seven_zip=None)
    with pytest.raises(ValueError, match="FORMAT_SERVICE_UNAVAILABLE"):
        convert_doc(b"\xd0\xcf\x11\xe0data", dependencies)


def test_offline_ocr_maps_text_and_boxes_without_model_download():
    import io

    from PIL import Image

    from efficiency_platform_agent.agents.hr.ocr import LocalHrOcr

    class Adapter:
        def recognize(self, content):
            return [{"rec_texts": ["Python开发"], "rec_boxes": [[1, 2, 8, 9]]}]

    image = io.BytesIO()
    Image.new("RGB", (10, 10)).save(image, format="PNG")
    blocks = LocalHrOcr(Adapter())(image.getvalue())
    assert blocks[0].text == "Python开发"
    assert blocks[0].bbox == (1.0, 2.0, 8.0, 9.0)


def test_doc_and_sevenzip_adapters_execute_safe_arguments_and_verify_output(
    tmp_path, monkeypatch
):
    import io
    import zipfile
    from pathlib import Path

    from efficiency_platform_agent.agents.hr import local_tools

    tools = local_tools.LocalToolDependencies(
        libreoffice="installed-soffice", seven_zip="installed-7z"
    )
    calls = []

    def command(arguments, folder, **kwargs):
        calls.append(arguments)
        if arguments[1] == "l":
            return "----------\nPath = resume.txt\nSize = 6\nPacked Size = 6\nFolder = -\nEncrypted = -\n"
        if arguments[1] == "x":
            target = Path(next(a[2:] for a in arguments if a.startswith("-o")))
            (target / "resume.txt").write_bytes(b"Python")
            return ""
        target = Path(arguments[arguments.index("--outdir") + 1]) / "source.docx"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", "<document/>")
        target.write_bytes(stream.getvalue())
        return ""

    monkeypatch.setattr(local_tools, "_command", command)
    assert local_tools.convert_doc(b"\xd0\xcf\x11\xe0data", tools).startswith(b"PK")
    assert "--headless" in calls[0] and "--nofirststartwizard" in calls[0]
    assert local_tools.unpack_archive(b"7z\xbc\xaf\x27\x1cdata", ".7z", tools) == [
        ("resume.txt", b"Python")
    ]
    assert calls[-1][1] == "x" and "--" in calls[-1]


def test_sevenzip_rejects_manifest_path_before_extract(monkeypatch):
    from efficiency_platform_agent.agents.hr import local_tools

    calls = []

    def command(arguments, folder, **kwargs):
        calls.append(arguments)
        return "----------\nPath = ../escape.txt\nSize = 3\nEncrypted = -\n"

    monkeypatch.setattr(local_tools, "_command", command)
    with pytest.raises(ValueError, match="HR_FILE_ARCHIVE_PATH"):
        local_tools.unpack_archive(
            b"7z\xbc\xaf\x27\x1cdata",
            ".7z",
            local_tools.LocalToolDependencies(seven_zip="installed-7z"),
        )
    assert len(calls) == 1
