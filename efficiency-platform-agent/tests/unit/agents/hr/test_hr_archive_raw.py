"""归档原件出口在返回前完成整包安全预检，不先解析或发送模型。"""

import base64
import hashlib
import io
import zipfile

import pytest

from efficiency_platform_agent.agents.hr.extraction import extract_archive_raw


def archive(name="folder/resume.txt", content=b"synthetic resume"):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(name, content)
    return target.getvalue()


def test_raw_archive_preserves_verified_bytes_and_hash():
    content = archive()
    result = extract_archive_raw(content, hashlib.sha256(content).hexdigest())
    assert len(result) == 1
    assert base64.b64decode(result[0]["content_base64"]) == b"synthetic resume"
    assert result[0]["sha256"] == hashlib.sha256(b"synthetic resume").hexdigest()


@pytest.mark.parametrize("name", ["../resume.txt", "C:/resume.txt", "nested.zip"])
def test_raw_archive_rejects_entire_unsafe_manifest(name):
    content = archive(name)
    with pytest.raises(ValueError):
        extract_archive_raw(content, hashlib.sha256(content).hexdigest())


def test_raw_archive_rejects_duplicate_names_and_ratio():
    content = archive("resume.txt", b"0" * 100000)
    with pytest.raises(ValueError, match="LIMIT"):
        extract_archive_raw(content, hashlib.sha256(content).hexdigest())


@pytest.mark.asyncio
async def test_extract_skill_raw_is_cpu_only_and_never_needs_model():
    from efficiency_platform_agent.agents.hr.service import HrSkillService
    from efficiency_platform_agent.contracts.hr import ExtractionInput, HrSkillRequest
    from efficiency_platform_agent.core.execution_control import RunControl

    content = archive()
    request = HrSkillRequest(
        run_id="raw",
        operation_id="raw",
        extraction=ExtractionInput(
            filename="batch.zip",
            content_base64=base64.b64encode(content).decode(),
            sha256=hashlib.sha256(content).hexdigest(),
            archive_raw=True,
        ),
    )
    result = await HrSkillService(None, None).execute(
        "hr.resume.extract", request, RunControl()
    )
    assert result["data"]["documents"][0]["filename"] == "folder/resume.txt"
