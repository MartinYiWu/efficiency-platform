"""正文获取只接受明确授权且经工具重新获取的原始证据。"""

import time
from importlib import import_module, util

import pytest

from efficiency_platform_agent.capabilities.research.v2.acquisition import (
    AcquisitionRuntimeContextV2,
)
from efficiency_platform_agent.contracts.research_sources_v2 import CandidateRecordV2
from efficiency_platform_agent.core.budget_execution import bind_budget_execution
from efficiency_platform_agent.providers.research.transport import PinnedResponse
from tests.unit.harness.test_research_local_tools import (
    REMAINING,
    Connector,
    setup,
    source,
)


def acquirer(case, descriptors):
    name = "efficiency_platform_agent.capabilities.research.v2.content_acquisition"
    assert util.find_spec(name) is not None, "CONTENT_ACQUIRER_MISSING"
    return import_module(name).ResearchContentAcquirer(case[0], descriptors=descriptors)


def candidate(**updates):
    values = {
        "candidate_id": "candidate-1",
        "source_id": "google_blog_rss",
        "source_item_id": "item-1",
        "url": "https://blog.google/article",
        "title": "Article",
        "discovered_via": "rss",
    }
    values.update(updates)
    return CandidateRecordV2(**values)


def context(case):
    return AcquisitionRuntimeContextV2(
        case[2],
        frozenset({"google_blog_rss", "hacker_news_api"}),
        frozenset({"research:read"}),
        REMAINING,
        time.monotonic() + 60,
    )


@pytest.mark.asyncio
async def test_acquirer_redirect_policy_denial_is_stable_without_retry_or_extra_budget():
    descriptor = source(body=True).model_copy(
        update={"content_endpoints": ("https://blog.google/article",)}
    )
    case = setup(
        descriptors=(descriptor,),
        connector=Connector(
            [PinnedResponse(302, {"location": "/private?download=all"}, ())]
        ),
    )
    with bind_budget_execution(case[1]), pytest.raises(ValueError) as raised:
        await acquirer(case, (descriptor,)).acquire(candidate(), context(case))
    assert raised.value.args == ("SOURCE_NOT_RUNTIME_ALLOWED",)
    assert len(case[3].calls) == 1
    assert len(case[4].calls) == 1
    assert (await case[1].port.snapshot(case[1].scope)).used.calls == 2


@pytest.mark.asyncio
async def test_acquires_original_document_via_tool_and_retains_no_cache():
    descriptors = (source(body=True),)
    case = setup(descriptors=descriptors)
    service = acquirer(case, descriptors)
    with bind_budget_execution(case[1]):
        document = await service.acquire(candidate(), context(case))
    assert document.text == "Original verified article body."
    assert document.candidate_id == "candidate-1"
    assert document.canonical_url == "https://blog.google/article"
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    ["summary", "no_body_permission", "foreign_host", "forged_full", "metadata_only"],
)
async def test_unapproved_evidence_never_reaches_transport(kind):
    descriptor = source(
        body=kind not in {"summary", "no_body_permission", "forged_full"}
    )
    if kind == "metadata_only":
        descriptor = descriptor.model_copy(
            update={
                "content_policy": descriptor.content_policy.model_copy(
                    update={"storage_mode": "metadata_only"}
                )
            }
        )
    descriptors = (descriptor,)
    case = setup(descriptors=descriptors)
    item = candidate()
    if kind in {"summary", "forged_full"}:
        item = candidate(
            content_scope="summary" if kind == "summary" else "full",
            inline_content="untrusted inline content",
        )
    if kind == "foreign_host":
        item = candidate(url="https://foreign.example/body")
    with bind_budget_execution(case[1]), pytest.raises(ValueError):
        await acquirer(case, descriptors).acquire(item, context(case))
    assert case[3].calls == []
    assert case[4].calls == []


@pytest.mark.asyncio
async def test_authorized_summary_candidate_refetches_full_article_via_runtime(
    monkeypatch,
):
    descriptors = (source(body=True),)
    case = setup(descriptors=descriptors)
    invocations = []
    original_invoke = case[0].invoke

    async def observe(request, *args, **kwargs):
        invocations.append(request.tool_name)
        return await original_invoke(request, *args, **kwargs)

    monkeypatch.setattr(case[0], "invoke", observe)
    item = candidate(
        content_scope="summary",
        inline_content="Only discovery summary, never body evidence",
    )
    with bind_budget_execution(case[1]):
        document = await acquirer(case, descriptors).acquire(item, context(case))
    assert document.text == "Original verified article body."
    assert item.inline_content not in document.text
    assert invocations and set(invocations) == {"research.fetch.v2"}
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://blog.google/unapproved?lang=en",
        "https://blog.google/article?lang=en&extra=1",
    ],
)
async def test_acquirer_rejects_same_host_unregistered_path_and_query_before_runtime(
    url, monkeypatch
):
    descriptor = source(body=True).model_copy(
        update={"content_endpoints": ("https://blog.google/article?lang=en",)}
    )
    case = setup(descriptors=(descriptor,))
    calls = []
    original_invoke = case[0].invoke

    async def observe(*args, **kwargs):
        calls.append("runtime")
        return await original_invoke(*args, **kwargs)

    monkeypatch.setattr(case[0], "invoke", observe)
    with (
        bind_budget_execution(case[1]),
        pytest.raises(ValueError, match="SOURCE_NOT_RUNTIME_ALLOWED"),
    ):
        await acquirer(case, (descriptor,)).acquire(candidate(url=url), context(case))
    assert calls == []
    assert case[3].calls == []
    assert case[4].calls == []


@pytest.mark.asyncio
async def test_same_candidate_id_cannot_reuse_other_tenant_document():
    descriptors = (source(body=True),)
    case = setup(descriptors=descriptors)
    service = acquirer(case, descriptors)
    with bind_budget_execution(case[1]):
        await service.acquire(candidate(), context(case))
        foreign = context(case)
        from dataclasses import replace

        foreign.run_context = replace(foreign.run_context, tenant_id="foreign")
        with pytest.raises(ValueError):
            await service.acquire(candidate(), foreign)
    assert len(case[3].calls) == 1


@pytest.mark.asyncio
async def test_platform_text_is_refetched_from_static_api_and_never_article():
    descriptors = (source("hacker_news_api", body=True),)
    body = b'{"id":123,"title":"Ask HN","text":"<p>Actual platform statement</p>","type":"story"}'
    case = setup(
        descriptors=descriptors,
        connector=Connector(
            [PinnedResponse(200, {"content-type": "application/json"}, (body,))]
        ),
    )
    item = candidate(
        source_id="hacker_news_api",
        source_item_id="123",
        url="https://news.ycombinator.com/item?id=123",
        content_scope="platform_text",
        inline_content="invented inline text",
        discovered_via="api",
    )
    with bind_budget_execution(case[1]):
        document = await acquirer(case, descriptors).acquire(item, context(case))
    assert document.text == "Actual platform statement"
    assert document.extractor_version.endswith("platform_text")
    assert case[3].calls[0].url == "https://hacker-news.firebaseio.com/v0/item/123.json"
    assert document.canonical_url == item.url


@pytest.mark.asyncio
async def test_platform_response_wrong_item_is_rejected():
    descriptors = (source("hacker_news_api", body=True),)
    case = setup(
        descriptors=descriptors,
        connector=Connector(
            [
                PinnedResponse(
                    200,
                    {"content-type": "application/json"},
                    (b'{"id":124,"text":"wrong item"}',),
                )
            ]
        ),
    )
    item = candidate(
        source_id="hacker_news_api",
        source_item_id="123",
        url="https://news.ycombinator.com/item?id=123",
        content_scope="platform_text",
        inline_content="inline",
        discovered_via="api",
    )
    with (
        bind_budget_execution(case[1]),
        pytest.raises(ValueError, match="SOURCE_SCHEMA_INVALID"),
    ):
        await acquirer(case, descriptors).acquire(item, context(case))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [b'{"id":123,"text":"private-body"', b"not-json-private-body", b"\xff"]
)
async def test_platform_malformed_json_returns_stable_error_without_raw_document(body):
    descriptors = (source("hacker_news_api", body=True),)
    case = setup(
        descriptors=descriptors,
        connector=Connector(
            [PinnedResponse(200, {"content-type": "application/json"}, (body,))]
        ),
    )
    item = candidate(
        source_id="hacker_news_api",
        source_item_id="123",
        url="https://news.ycombinator.com/item?id=123",
        content_scope="platform_text",
        inline_content="inline",
        discovered_via="api",
    )
    with bind_budget_execution(case[1]), pytest.raises(ValueError) as raised:
        await acquirer(case, descriptors).acquire(item, context(case))
    assert type(raised.value) is ValueError
    assert raised.value.args == ("SOURCE_SCHEMA_INVALID",)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert not hasattr(raised.value, "doc")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "media,body",
    [
        (
            "application/rss+xml",
            b"<rss><channel><title>Only summary</title></channel></rss>",
        ),
        ("application/json", b'{"abstract":"Only abstract"}'),
    ],
)
async def test_structured_discovery_payload_is_never_article_fulltext(media, body):
    descriptors = (source(body=True),)
    case = setup(
        descriptors=descriptors,
        connector=Connector([PinnedResponse(200, {"content-type": media}, (body,))]),
    )
    with (
        bind_budget_execution(case[1]),
        pytest.raises(ValueError, match="CONTENT_NOT_ARTICLE"),
    ):
        await acquirer(case, descriptors).acquire(candidate(), context(case))
