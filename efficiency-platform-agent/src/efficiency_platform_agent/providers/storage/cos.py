"""腾讯云 COS Artifact 隔离对象适配器；仅通过注入客户端执行调用。"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from typing import Any

_ID = re.compile(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?")
_MAX_OBJECTS = 3
_MAX_BYTES = 1 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArtifactPutRequest:
    run_stamp: str
    tenant_id: str
    artifact_id: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ArtifactGetRequest:
    run_stamp: str
    tenant_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArtifactSignRequest:
    run_stamp: str
    tenant_id: str
    artifact_id: str
    expires_seconds: int = 300


@dataclass(frozen=True, slots=True)
class ArtifactDeleteRequest:
    run_stamp: str
    tenant_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    run_stamp: str
    tenant_id: str
    artifact_id: str
    key: str
    size_bytes: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class SignedArtifact:
    record: ArtifactRecord
    url: str


class CosArtifactProvider:
    """在精确 run 前缀下管理最多三个合成 Artifact。"""

    def __init__(
        self, client: Any, *, bucket: str, region: str, max_concurrency: int = 2
    ) -> None:
        if client is None or not bucket.strip() or not region.strip():
            raise ValueError("client、bucket和region不能为空")
        self.client, self.bucket, self.region = client, bucket, region
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._records: dict[str, ArtifactRecord] = {}

    def _key(self, run_stamp: str, tenant_id: str, artifact_id: str) -> str:
        for name, value in (
            ("run_stamp", run_stamp),
            ("tenant_id", tenant_id),
            ("artifact_id", artifact_id),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or "\\" in value
                or "/" in value
                or ".." in value
                or _ID.fullmatch(value) is None
            ):
                raise ValueError(f"{name}格式无效")
        tenant_hash = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
        return f"s7/{run_stamp}/{tenant_hash}/{artifact_id}"

    async def _call(self, method: str, **kwargs: Any) -> Any:
        operation = getattr(self.client, method, None)
        if not callable(operation):
            raise TypeError("COS_METHOD_NOT_AVAILABLE")
        async with self._semaphore:
            return await asyncio.to_thread(operation, **kwargs)

    def _record(self, request: Any, content: bytes = b"") -> ArtifactRecord:
        key = self._key(request.run_stamp, request.tenant_id, request.artifact_id)
        if key in self._records:
            raise ValueError("ARTIFACT_ALREADY_EXISTS")
        if key not in self._records and len(self._records) >= _MAX_OBJECTS:
            raise ValueError("ARTIFACT_LIMIT_EXCEEDED")
        if len(content) > _MAX_BYTES:
            raise ValueError("ARTIFACT_SIZE_EXCEEDED")
        return ArtifactRecord(
            request.run_stamp,
            request.tenant_id,
            request.artifact_id,
            key,
            len(content),
            hashlib.sha256(content).hexdigest(),
        )

    async def put(self, request: ArtifactPutRequest) -> ArtifactRecord:
        if not isinstance(request, ArtifactPutRequest):
            raise TypeError("request必须是ArtifactPutRequest")
        record = self._record(request, request.content)
        await self._call(
            "put_object", Bucket=self.bucket, Key=record.key, Body=request.content
        )
        self._records[record.key] = record
        return record

    async def head(self, request: ArtifactGetRequest) -> ArtifactRecord:
        record = self._records.get(
            self._key(request.run_stamp, request.tenant_id, request.artifact_id)
        )
        if record is None:
            raise KeyError("ARTIFACT_NOT_FOUND")
        await self._call("head_object", Bucket=self.bucket, Key=record.key)
        return record

    async def get(self, request: ArtifactGetRequest) -> bytes:
        record = await self.head(request)
        result = await self._call("get_object", Bucket=self.bucket, Key=record.key)
        body = (
            result.get("Body")
            if isinstance(result, dict)
            else getattr(result, "Body", None)
        )
        if body is None or not hasattr(body, "read"):
            raise ValueError("COS响应缺少对象内容")
        read = body.read
        if not callable(read):
            raise TypeError("COS响应对象不可读取")
        content = read()
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError("COS响应内容类型无效")
        value = bytes(content)
        if hashlib.sha256(value).hexdigest() != record.content_sha256:
            raise ValueError("ARTIFACT_INTEGRITY_FAILED")
        return value

    async def sign_download(self, request: ArtifactSignRequest) -> SignedArtifact:
        if request.expires_seconds <= 0:
            raise ValueError("expires_seconds必须为正数")
        record = await self.head(
            ArtifactGetRequest(
                request.run_stamp, request.tenant_id, request.artifact_id
            )
        )
        url = await self._call(
            "get_presigned_url",
            Method="GET",
            Bucket=self.bucket,
            Key=record.key,
            Expired=request.expires_seconds,
        )
        return SignedArtifact(record, str(url))

    async def delete(self, request: ArtifactDeleteRequest) -> None:
        key = self._key(request.run_stamp, request.tenant_id, request.artifact_id)
        await self._call("delete_object", Bucket=self.bucket, Key=key)
        self._records.pop(key, None)


__all__ = [
    "ArtifactDeleteRequest",
    "ArtifactGetRequest",
    "ArtifactPutRequest",
    "ArtifactRecord",
    "ArtifactSignRequest",
    "CosArtifactProvider",
    "SignedArtifact",
]
