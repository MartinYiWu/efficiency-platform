"""上传请求的最小边界契约。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UploadMetadata:
    upload_id: str
    tenant_id: str
    filename: str
    mime_type: str


__all__ = ["UploadMetadata"]
