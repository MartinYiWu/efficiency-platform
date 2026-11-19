from dataclasses import replace

import pytest

from efficiency_platform_agent.core.memory import ConversationScope, SourceDependency
from efficiency_platform_agent.memory.episodes import (
    EpisodeContent,
    EpisodeEvidence,
    validate_episode,
)
from efficiency_platform_agent.memory.promotion import (
    PromotionEvidence,
    validate_promotion,
)


def test_likes_or_model_claims_cannot_prove_measured_results_or_hr_profiles():
    content = EpisodeContent(
        category="USER_PREFERENCE",
        scenario="s",
        preconditions=(),
        actions=("a",),
        observed_results="preferred",
        evidence_refs=("r",),
        applicable_version="1",
        disallowed_conditions=(),
    )
    dep = SourceDependency("USER_PREFERENCE_DECISION", "r", "1")
    evidence = EpisodeEvidence(
        ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s"),
        (dep,),
        frozenset({"r"}),
        frozenset(),
    )
    assert validate_episode(content, evidence).status == "CANDIDATE"
    with pytest.raises(ValueError, match="MEMORY_EPISODE_MEASUREMENT_REQUIRED"):
        validate_episode(
            content.model_copy(update={"category": "MEASURED_RESULT"}), evidence
        )
    with pytest.raises(ValueError, match="MEMORY_EPISODE_HR_PROFILE_DENIED"):
        validate_episode(
            content,
            replace(
                evidence,
                scope=ConversationScope("t", "u", "hr", "hr", "TASK_ONLY", None),
            ),
        )


def test_promotion_requires_current_source_independent_approval_and_complete_regression():
    dep = SourceDependency("USER_PREFERENCE_DECISION", "r", "1")
    evidence = PromotionEvidence(
        "episode",
        "a" * 64,
        (dep,),
        (dep,),
        True,
        True,
        True,
        "fixed",
        "1",
        "b" * 64,
        10,
        10,
        10,
        "reviewer",
        "owner",
    )
    validate_promotion(evidence)
    for invalid, code in (
        (replace(evidence, current_dependencies=()), "SOURCE_REVOKED"),
        (replace(evidence, passed=9), "REGRESSION_REQUIRED"),
        (replace(evidence, reviewed_by="owner"), "INDEPENDENT_REVIEW_REQUIRED"),
        (replace(evidence, sharing_approved=False), "APPROVAL_REQUIRED"),
    ):
        with pytest.raises(ValueError, match=code):
            validate_promotion(invalid)
