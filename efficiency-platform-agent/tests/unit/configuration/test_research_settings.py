"""R01 研究配置默认关闭与严格 Schema 测试。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.configuration.research import (
    ResearchPolicySettings,
    ResearchSourceSettings,
)

ROOT = Path(__file__).parents[3]


def test_checked_in_source_candidates_match_live_admission_decisions() -> None:
    settings = ResearchSourceSettings.load(ROOT / "config" / "research_sources.toml")

    assert len(settings.sources) == 5
    assert {item.adapter_id for item in settings.sources} == {
        "rss_atom",
        "hacker_news",
        "arxiv",
        "gdelt",
    }
    enabled = {item.source_id for item in settings.sources if item.enabled}
    assert enabled == {
        "fixture_official_feed",
        "fixture_github_releases",
        "fixture_hacker_news",
    }
    assert {item.source_id: item.cost_mode for item in settings.sources} == {
        "fixture_official_feed": "free",
        "fixture_arxiv": "free",
        "fixture_gdelt": "free",
        "fixture_github_releases": "free",
        "fixture_hacker_news": "free",
    }
    assert {
        item.source_id
        for item in settings.sources
        if item.admission_status == "VERIFIED"
    } == enabled
    assert {
        item.source_id
        for item in settings.sources
        if item.admission_status == "UNVERIFIED"
    } == {"fixture_arxiv", "fixture_gdelt"}
    assert all(item.credential_source_id is None for item in settings.sources)


def test_policy_config_has_bounded_offline_defaults() -> None:
    policy = ResearchPolicySettings.load(ROOT / "config" / "research_policies.toml")
    assert policy.max_collection_rounds == 3
    assert policy.max_no_gain_rounds == 1


def test_module_path_or_unknown_adapter_cannot_be_loaded() -> None:
    with pytest.raises(ValidationError):
        ResearchSourceSettings.model_validate(
            {
                "config_version": "bad",
                "sources": [
                    {
                        "source_id": "evil",
                        "adapter_id": "package.module:Factory",
                        "enabled": True,
                        "module_path": "package.module",
                    }
                ],
            }
        )
