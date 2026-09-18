"""经 research.fetch.v2 重获准入正文；发现摘要本身从不充当正文。"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

from efficiency_platform_agent.contracts.research_sources_v2 import (
    CandidateRecordV2,
    ExtractedDocumentV2,
    FetchedContentV2,
    SourceDescriptorV2,
)
from efficiency_platform_agent.contracts.research_transport_v2 import (
    ResearchUrlSourcePolicyV2,
)
from efficiency_platform_agent.core.run import JsonObject, ToolRequest
from efficiency_platform_agent.providers.research._adapter_support import clean_fragment
from efficiency_platform_agent.providers.research.extraction import DocumentExtractor
from efficiency_platform_agent.security.url_policy import UrlPolicy
from efficiency_platform_agent.tools.external.research import (
    ResearchFetchedResultV2,
    _thaw,
)
from efficiency_platform_agent.tools.runtime.service import ToolRuntime

from .acquisition import AcquisitionRuntimeContextV2


def validate_content_endpoint(descriptor: SourceDescriptorV2, url: str) -> None:
    """正文端点须事先登记完整 URL，精确匹配路径及有序查询串。

    不支持通配符、路径前缀或动态查询参数；无查询、查询值、顺序、重复键
    与编码方式均不能由发现内容扩大。重定向每一跳重新执行同一检查。
    """
    if url not in descriptor.content_endpoints:
        raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")
    try:
        shape = UrlPolicy().validate_shape(
            url, ResearchUrlSourcePolicyV2(allowed_hosts=descriptor.allowed_hosts)
        )
    except ValueError:
        raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED") from None
    if shape.url != url:
        raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")


class ResearchContentAcquirer:
    """不保存正文缓存，结果仅交付当前 Run 隔离事实库。"""

    def __init__(
        self,
        runtime: ToolRuntime,
        *,
        descriptors: tuple[SourceDescriptorV2, ...],
        extractor: DocumentExtractor | None = None,
    ) -> None:
        self.runtime = runtime
        self.descriptors = {item.source_id: item for item in descriptors}
        self.extractor = extractor or DocumentExtractor(max_body_bytes=1024 * 1024)

    async def acquire(
        self, candidate: CandidateRecordV2, context: AcquisitionRuntimeContextV2
    ) -> ExtractedDocumentV2:
        candidate = CandidateRecordV2.model_validate(candidate.model_dump())
        descriptor = self.descriptors.get(candidate.source_id)
        if (
            descriptor is None
            or not descriptor.enabled
            or candidate.source_id not in context.allowed_source_ids
        ):
            raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")
        if descriptor.content_policy.storage_mode == "metadata_only":
            raise ValueError("CONTENT_NOT_APPROVED")
        platform = candidate.content_scope == "platform_text"
        required_use = "platform_text" if platform else "article_body"
        if required_use not in descriptor.admission.intended_uses:
            raise ValueError("CONTENT_NOT_APPROVED")
        if platform:
            if (
                descriptor.adapter_id != "hacker_news"
                or not candidate.source_item_id.isascii()
                or not candidate.source_item_id.isdigit()
            ):
                raise ValueError("CONTENT_NOT_APPROVED")
            url = f"https://hacker-news.firebaseio.com/v0/item/{candidate.source_item_id}.json"
            canonical = (
                f"https://news.ycombinator.com/item?id={candidate.source_item_id}"
            )
            if candidate.url != canonical:
                raise ValueError("SOURCE_NOT_RUNTIME_ALLOWED")
        else:
            url = candidate.url
        validate_content_endpoint(descriptor, url)
        remaining_ms = int((context.deadline_monotonic - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise ValueError("TOOL_TIMEOUT")
        request_id = f"content-{uuid4().hex}"
        request = ToolRequest(
            "2",
            "research.fetch.v2",
            JsonObject(
                (
                    ("request_id", request_id),
                    ("source_id", candidate.source_id),
                    ("candidate_id", candidate.candidate_id),
                    ("url", url),
                    ("etag", None),
                    ("last_modified", None),
                )
            ),
            min(10_000, remaining_ms),
            None,
            request_id,
            False,
            2 * 1024 * 1024,
        )
        lease = context.lease_context
        # 并行文档不得复用同一预约 ID；共享父账本及最新版本。
        local_lease = (
            replace(lease, invocation_prefix=request_id) if lease is not None else None
        )
        result, records = await self.runtime.invoke(
            request,
            context.run_context,
            allowed_tools=frozenset({"research.fetch.v2"}),
            granted_permissions=context.granted_permissions,
            remaining_budget=context.remaining_budget,
            lease_context=local_lease,
        )
        if lease is not None and local_lease is not None:
            lease.version = max(lease.version, local_lease.version)
        context.remaining_budget = replace(
            context.remaining_budget,
            tool_calls=max(0, context.remaining_budget.tool_calls - len(records)),
        )
        if result.error is not None:
            raise ValueError(result.error.code)
        if time.monotonic() >= context.deadline_monotonic:
            raise ValueError("TOOL_TIMEOUT")
        raw = ResearchFetchedResultV2.model_validate(_thaw(result.output))
        if raw.request_id != request_id or raw.candidate_id != candidate.candidate_id:
            raise ValueError("SOURCE_SCHEMA_INVALID")
        body = base64.b64decode(raw.body_base64, validate=True)
        content = FetchedContentV2(
            request_id=request_id,
            candidate_id=candidate.candidate_id,
            final_url=raw.final_url,
            media_type=raw.media_type,
            body=body,
            downloaded_bytes=raw.downloaded_bytes,
            request_count=raw.request_count,
            fetched_at=datetime.fromisoformat(raw.fetched_at),
            status_code=raw.status_code,
        )
        if platform:
            if (
                raw.media_type != "application/json"
                or urlsplit(raw.final_url).path != urlsplit(url).path
            ):
                raise ValueError("SOURCE_SCHEMA_INVALID")
            value = None
            try:
                value = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                # 在异常处理块外抛稳定错误，避免异常链携带原始文档。
                pass
            if (
                not isinstance(value, dict)
                or type(value.get("id")) is not int
                or str(value["id"]) != candidate.source_item_id
                or value.get("deleted")
                or value.get("dead")
            ):
                raise ValueError("SOURCE_SCHEMA_INVALID")
            text = clean_fragment(value.get("text"))
            if not text:
                raise ValueError("CONTENT_UNAVAILABLE")
            return ExtractedDocumentV2(
                candidate_id=candidate.candidate_id,
                canonical_url=candidate.url,
                title=candidate.title,
                text=text,
                content_hash=hashlib.sha256(body).hexdigest(),
                extractor_version="research-content/2:platform_text",
            )
        if raw.media_type not in {"text/html", "text/plain"}:
            raise ValueError("CONTENT_NOT_ARTICLE")
        return self.extractor.extract(content)


__all__ = ["ResearchContentAcquirer", "validate_content_endpoint"]
