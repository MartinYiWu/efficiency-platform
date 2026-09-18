"""本地实时来源的静态身份与失败关闭准入测试。"""

from datetime import UTC, datetime, timedelta
from importlib import import_module, util
from pathlib import Path

import pytest

from efficiency_platform_agent.contracts.research_sources_v2 import SourceDescriptorV2
from tests.unit.capabilities.research_v2.test_source_registry import brief, context

CONFIG = Path(__file__).resolve().parents[3] / "config/research_local_live_sources.toml"
NOW = datetime(2026, 9, 17, 14, tzinfo=UTC)


def _module():
    name = "efficiency_platform_agent.configuration.research_local_sources"
    assert util.find_spec(name) is not None, "LOCAL_SOURCE_DESCRIPTOR_LOADER_MISSING"
    return import_module(name)


def _sources():
    return _module().load_local_source_descriptors(CONFIG)


def _registry():
    name = "efficiency_platform_agent.harness.research_local_sources"
    assert util.find_spec(name) is not None, "LOCAL_SOURCE_REGISTRY_COMPOSITION_MISSING"
    return import_module(name)


def test_configuration_does_not_construct_capability_registry():
    assert not hasattr(_module(), "build_local_source_registry")


def _active_source():
    source = next(item for item in _sources() if item.source_id == "google_blog_rss")
    return source.model_copy(
        update={
            "enabled": True,
            "freshness_sla": timedelta(days=7),
            "max_lookback": timedelta(days=30),
            "admission": source.admission.model_copy(update={"history_verified": True}),
        }
    )


def _history_source(
    history_mode: str,
    *,
    history_verified: bool = True,
    freshness_sla: timedelta | None = timedelta(days=7),
    max_lookback: timedelta | None = timedelta(days=30),
):
    source = _active_source()
    return source.model_copy(
        update={
            "history_mode": history_mode,
            "freshness_sla": freshness_sla,
            "max_lookback": max_lookback,
            "admission": source.admission.model_copy(
                update={"history_verified": history_verified}
            ),
        }
    )


def _history_brief(source_id: str):
    request_brief = brief(source_ids=(source_id,))
    return request_brief.model_copy(
        update={
            "source_constraints": request_brief.source_constraints.model_copy(
                update={
                    "languages": None,
                    "event_regions": None,
                    "primary_only": False,
                }
            )
        }
    )


def test_real_sources_have_complete_descriptors_and_closed_content_permissions():
    sources = _sources()
    assert {item.source_id for item in sources} == {
        "google_blog_rss",
        "langgraph_releases_atom",
        "hacker_news_api",
        "arxiv_api",
        "gdelt_doc_api",
    }
    assert all(isinstance(item, SourceDescriptorV2) for item in sources)
    assert all(not item.enabled for item in sources)
    assert all(item.content_policy.storage_mode != "full" for item in sources)
    assert all(not item.admission.history_verified for item in sources)
    assert {
        item.source_id for item in sources if item.admission.status == "VERIFIED"
    } == {
        "google_blog_rss",
        "langgraph_releases_atom",
        "hacker_news_api",
    }


@pytest.mark.parametrize(
    "source_id", ["fixture_official_feed", "https://evil.test/rss"]
)
def test_fixture_or_discovered_url_cannot_register_as_local_source(source_id):
    source = _active_source().model_copy(update={"source_id": source_id})
    with pytest.raises(ValueError, match="LOCAL_SOURCE_ID_NOT_REGISTERED"):
        _registry().build_local_source_registry((source,), now=NOW)


def test_unknown_host_cannot_be_added_to_registered_source():
    source = _active_source().model_copy(update={"allowed_hosts": ("evil.test",)})
    with pytest.raises(ValueError, match="LOCAL_SOURCE_HOST_NOT_REGISTERED"):
        _registry().build_local_source_registry((source,), now=NOW)


@pytest.mark.parametrize("failure", ["expired", "unknown_cost", "empty_use"])
def test_enabled_cannot_bypass_admission(failure):
    source = _active_source()
    if failure == "expired":
        source = source.model_copy(
            update={
                "admission": source.admission.model_copy(
                    update={"last_verified_at": NOW - timedelta(days=31)}
                )
            }
        )
        reason = "SOURCE_ADMISSION_EXPIRED"
    elif failure == "unknown_cost":
        source = source.model_copy(
            update={
                "cost_policy": source.cost_policy.model_copy(update={"mode": "unknown"})
            }
        )
        reason = "SOURCE_COST_UNVERIFIED"
    else:
        source = source.model_copy(
            update={
                "admission": source.admission.model_copy(update={"intended_uses": ()})
            }
        )
        reason = "SOURCE_USE_UNVERIFIED"
    with pytest.raises(ValueError, match=reason):
        _registry().build_local_source_registry((source,), now=NOW)


def test_only_enabling_unprobed_source_is_rejected():
    source = next(item for item in _sources() if item.source_id == "arxiv_api")
    with pytest.raises(ValueError, match="SOURCE_UNVERIFIED"):
        _registry().build_local_source_registry(
            (source.model_copy(update={"enabled": True}),), now=NOW
        )


@pytest.mark.parametrize("history_mode", ["latest_only", "queryable", "archive"])
@pytest.mark.parametrize(
    "missing_history_evidence",
    ["history_verified", "freshness_sla", "max_lookback"],
)
def test_enabled_history_source_rejects_before_reservation_or_network(
    history_mode, missing_history_evidence
):
    overrides = {
        "history_verified": True,
        "freshness_sla": timedelta(days=7),
        "max_lookback": timedelta(days=30),
    }
    if missing_history_evidence == "history_verified":
        overrides[missing_history_evidence] = False
    else:
        overrides[missing_history_evidence] = None
    source = _history_source(history_mode, **overrides)
    network_calls = []

    with pytest.raises(ValueError, match="SOURCE_HISTORY_UNSUPPORTED"):
        registry = _registry().build_local_source_registry((source,), now=NOW)
        decision = registry.reserve_for_call(
            source.source_id,
            context(now=NOW, allowed_source_ids=(source.source_id,)),
            _history_brief(source.source_id),
        )
        if decision.allowed:
            network_calls.append(source.source_id)

    assert network_calls == []


@pytest.mark.parametrize("history_mode", ["latest_only", "queryable", "archive"])
def test_verified_bounded_history_source_can_build_and_reserve(history_mode):
    source = _history_source(history_mode)
    registry = _registry().build_local_source_registry((source,), now=NOW)
    decision = registry.reserve_for_call(
        source.source_id,
        context(now=NOW, allowed_source_ids=(source.source_id,)),
        _history_brief(source.source_id),
    )

    assert decision.allowed


def test_registry_rechecks_admission_when_runtime_time_advances():
    source = _active_source()
    registry = _registry().build_local_source_registry((source,), now=NOW)
    decision = registry.reserve_for_call(
        source.source_id,
        context(now=NOW + timedelta(days=31), allowed_source_ids=(source.source_id,)),
        brief(source_ids=(source.source_id,)),
    )
    assert decision.reason_code == "SOURCE_ADMISSION_EXPIRED"


def test_config_unknown_fields_and_incomplete_descriptor_are_rejected(tmp_path):
    _module()
    original = CONFIG.read_text(encoding="utf-8")
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace('publisher_id = "google"', 'untrusted = "google"'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        _module().load_local_source_descriptors(path)
