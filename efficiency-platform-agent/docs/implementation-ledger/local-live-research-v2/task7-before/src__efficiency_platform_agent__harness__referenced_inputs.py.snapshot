"""在会话模型调用前校验并裁剪上一轮排名引用。"""

import json
import re

from efficiency_platform_agent.capabilities.quality.deliverable_v2 import (
    assemble_set_v2,
)
from efficiency_platform_agent.contracts.deliverables import DeliverableSetV2
from efficiency_platform_agent.contracts.intent import (
    IntentEnvelopeV1,
    IntentRequirementsV1,
)
from efficiency_platform_agent.contracts.referenced_inputs import ReferencedRankedInput
from efficiency_platform_agent.contracts.responses import RunViewV1
from efficiency_platform_agent.core.enums import RunStatus
from efficiency_platform_agent.harness.errors import HarnessError

_RANK = re.compile(r"第\s*([+-]?[0-9]+)\s*条")
_REWRITE = ("改写", "改成", "写成")
_PLATFORMS = (
    ("小红书", "xiaohongshu"),
    ("公众号", "wechat_official_account"),
    ("头条", "toutiao"),
    ("xiaohongshu", "xiaohongshu"),
    ("wechat_official_account", "wechat_official_account"),
    ("toutiao", "toutiao"),
)


def requested_rank(message: str) -> int | None:
    """只处理明确序号改写，不猜测自由语义中的指代。"""
    matches = _RANK.findall(message)
    if not matches or not any(word in message for word in _REWRITE):
        return None
    if len(matches) != 1:
        raise reference_error()
    return int(matches[0])


def reference_error() -> HarnessError:
    return HarnessError(
        "CONVERSATION_REFERENCE_UNAVAILABLE",
        "上一轮没有可引用的有效排名条目，请提供条目内容或先完成排名摘要。",
        category="request",
    )


def select_ranked_reference(
    view: RunViewV1,
    rank: int,
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
) -> ReferencedRankedInput:
    """严格读取 V2 与来源闭包，任何失败均拒绝而不搜索更早的 Run。"""
    if view.status is not RunStatus.SUCCEEDED or not isinstance(view.output, dict):
        raise reference_error()
    try:
        value = assemble_set_v2(
            DeliverableSetV2.model_validate_json(
                json.dumps(view.output.get("deliverable_set")),
                strict=True,
            )
        )
        if value.run_id != view.run_id:
            raise ValueError("REFERENCE_RUN_MISMATCH")
        digests = [d for d in value.deliverables if d.content.kind == "ranked_digest"]
        if len(digests) != 1:
            raise ValueError("REFERENCE_DIGEST_AMBIGUOUS")
        digest = digests[0]
        items = digest.content.items
        if len({i.item_id for i in items}) != len(items):
            raise ValueError("REFERENCE_ITEM_DUPLICATED")
        ids = [c.citation_id for c in digest.citations]
        if len(ids) != len(set(ids)):
            raise ValueError("REFERENCE_CITATION_DUPLICATED")
        selected = next(i for i in items if i.rank == rank)
        by_id = {c.citation_id: c for c in digest.citations}
        source_refs = selected.source_refs
        if len(source_refs) != len(set(source_refs)):
            raise ValueError("REFERENCE_CITATION_DUPLICATED")
        if not set(source_refs).issubset(by_id):
            raise ValueError("REFERENCE_CITATION_CLOSURE_INVALID")
        original_citations = tuple(by_id[ref] for ref in source_refs)
        if any(
            selected.item_id not in citation.supports_item_ids
            for citation in original_citations
        ):
            raise ValueError("REFERENCE_ITEM_CLOSURE_INVALID")
        citations = tuple(
            citation.model_copy(
                deep=True, update={"supports_item_ids": [selected.item_id]}
            )
            for citation in original_citations
        )
        return ReferencedRankedInput(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            source_run_id=view.run_id,
            source_deliverable_id=digest.deliverable_id,
            item=selected.model_copy(deep=True),
            citations=citations,
        )
    except (ValueError, StopIteration, KeyError, TypeError, AttributeError) as error:
        raise reference_error() from error


def rewrite_intent(message: str) -> IntentEnvelopeV1:
    """只从本轮显式平台构建改写任务，不让研究历史触发重新联网。"""
    platforms = tuple(
        dict.fromkeys(value for alias, value in _PLATFORMS if alias in message)
    )
    if not platforms:
        raise HarnessError(
            "CONVERSATION_REFERENCE_PLATFORM_REQUIRED",
            "请补充上一轮条目要改写到的平台：小红书、公众号或头条。",
            category="request",
        )
    return IntentEnvelopeV1(
        domain="content",
        goal=message,
        task_type="multi_platform_content",
        channels=list(platforms),
        needs_multi_agent=True,
        confidence=1,
        requirements=IntentRequirementsV1(topic=message, platforms=platforms),
    )
