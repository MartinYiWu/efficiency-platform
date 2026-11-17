"""本机已安装文档工具的有界进程适配，不安装、不下载。"""

import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class LocalToolDependencies:
    libreoffice: str | None = None
    seven_zip: str | None = None

    @classmethod
    def detect(cls) -> "LocalToolDependencies":
        office = shutil.which("soffice") or shutil.which("libreoffice")
        seven = shutil.which("7zz") or shutil.which("7z")
        program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        if (
            office is None
            and (program_files / "LibreOffice/program/soffice.exe").is_file()
        ):
            office = str(program_files / "LibreOffice/program/soffice.exe")
        if seven is None and (program_files / "7-Zip/7z.exe").is_file():
            seven = str(program_files / "7-Zip/7z.exe")
        return cls(office, seven)


def _command(
    arguments: list[str], folder: Path, *, limit: int = 2 * 1024 * 1024
) -> str:
    executable = Path(arguments[0])
    if not executable.is_file():
        raise ValueError("FORMAT_SERVICE_UNAVAILABLE")
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper()
        in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "PATH")
    }
    process = subprocess.Popen(
        arguments,
        cwd=folder,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    timer = threading.Timer(30, process.kill)
    timer.start()
    output = bytearray()
    try:
        assert process.stdout is not None
        while data := process.stdout.read(65536):
            if len(output) + len(data) > limit:
                process.kill()
                raise ValueError("HR_FILE_TOOL_OUTPUT_LIMIT")
            output.extend(data)
        if process.wait(timeout=2) != 0:
            raise ValueError("HR_FILE_LOCAL_TOOL_FAILED")
        return output.decode("utf-8", errors="replace")
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        if process.stdout:
            process.stdout.close()


def convert_doc(
    content: bytes, dependencies: LocalToolDependencies | None = None
) -> bytes:
    tools = dependencies or LocalToolDependencies.detect()
    if tools.libreoffice is None:
        raise ValueError("FORMAT_SERVICE_UNAVAILABLE:DOC")
    if not content.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError("HR_FILE_MAGIC_INVALID")
    with tempfile.TemporaryDirectory(prefix="hr-doc-") as temporary:
        root = Path(temporary)
        source = root / "source.doc"
        source.write_bytes(content)
        output = root / "output"
        output.mkdir()
        profile = root / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user/registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Writer/Content/Update"><prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item></oor:items>',
            encoding="utf-8",
        )
        _command(
            [
                tools.libreoffice,
                "-env:UserInstallation=" + profile.as_uri(),
                "--headless",
                "--nologo",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to",
                "docx",
                "--outdir",
                str(output),
                str(source),
            ],
            root,
        )
        target = output / "source.docx"
        if (
            not target.is_file()
            or target.is_symlink()
            or target.stat().st_size > 20 * 1024 * 1024
        ):
            raise ValueError("HR_FILE_DOC_CONVERSION_FAILED")
        return target.read_bytes()


def unpack_archive(
    content: bytes, extension: str, dependencies: LocalToolDependencies | None = None
) -> list[tuple[str, bytes]]:
    tools = dependencies or LocalToolDependencies.detect()
    if tools.seven_zip is None:
        raise ValueError("FORMAT_SERVICE_UNAVAILABLE:ARCHIVE")
    signatures = {".rar": (b"Rar!\x1a\x07",), ".7z": (b"7z\xbc\xaf\x27\x1c",)}
    if extension not in signatures or not content.startswith(signatures[extension]):
        raise ValueError("HR_FILE_MAGIC_INVALID")
    with tempfile.TemporaryDirectory(prefix="hr-archive-") as temporary:
        root = Path(temporary)
        source = root / ("source" + extension)
        source.write_bytes(content)
        listing = _command(
            [tools.seven_zip, "l", "-slt", "-sccUTF-8", "--", str(source)], root
        )
        if "----------" not in listing:
            raise ValueError("HR_FILE_ARCHIVE_MANIFEST_INVALID")
        entries = []
        for record in listing.split("----------", 1)[1].strip().split("\n\n"):
            fields = dict(
                line.split(" = ", 1) for line in record.splitlines() if " = " in line
            )
            if fields:
                entries.append(fields)
        total = 0
        count = 0
        names: set[str] = set()
        for item in entries:
            name = item.get("Path", "").replace("\\", "/")
            path = PurePosixPath(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or ":" in name
                or len(path.parts) > 8
                or name.casefold() in names
                or item.get("Encrypted") == "+"
                or any(key in item for key in ("Symbolic Link", "Hard Link"))
                or "l" in item.get("Mode", "")
            ):
                raise ValueError("HR_FILE_ARCHIVE_PATH_INVALID")
            names.add(name.casefold())
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
            size = int(item.get("Size", "0"))
            if size < 0 or size > 20 * 1024 * 1024:
                raise ValueError("HR_FILE_ARCHIVE_LIMIT")
            total += size
            if item.get("Folder") != "+" and not item.get("Attributes", "").startswith(
                "D"
            ):
                count += 1
        if (
            not count
            or count > 100
            or total > 500 * 1024 * 1024
            or total > max(1, len(content)) * 100
        ):
            raise ValueError("HR_FILE_ARCHIVE_LIMIT")
        output = root / "output"
        output.mkdir()
        _command(
            [tools.seven_zip, "x", "-y", "-p", "-o" + str(output), "--", str(source)],
            root,
        )
        files: list[tuple[str, bytes]] = []
        actual_total = 0
        for target in output.rglob("*"):
            if target.is_symlink() or not target.resolve().is_relative_to(
                output.resolve()
            ):
                raise ValueError("HR_FILE_ARCHIVE_PATH_INVALID")
            if target.is_file():
                size = target.stat().st_size
                actual_total += size
                if (
                    size > 20 * 1024 * 1024
                    or actual_total > 500 * 1024 * 1024
                    or len(files) >= 100
                ):
                    raise ValueError("HR_FILE_ARCHIVE_LIMIT")
                name = target.relative_to(output).as_posix()
                if name.casefold() not in names:
                    raise ValueError("HR_FILE_ARCHIVE_MANIFEST_MISMATCH")
                files.append((name, target.read_bytes()))
        if len(files) != count or actual_total != total:
            raise ValueError("HR_FILE_ARCHIVE_MANIFEST_MISMATCH")
        return files
