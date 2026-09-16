"""ChannelProfile 到平台执行视图的确定性解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from efficiency_platform_agent.agents.operation.contracts.profiles import (
    ChannelProfile,
    ProfileFactState,
    ProfileKind,
    ProfileReference,
)
from efficiency_platform_agent.core.run import JsonObject


@dataclass(frozen=True, slots=True)
class PlatformProfile:
    """单个平台的不可变执行规则视图，仅允许固定样本使用。"""

    contract_version: Literal["platform-profile/1"]
    profile_reference: ProfileReference
    channel_id: str
    rules_version: str
    content_structure: tuple[str, ...]
    tone_rules: tuple[str, ...]
    length_limits: JsonObject
    formatting_rules: tuple[str, ...]
    tag_rules: tuple[str, ...]
    factual_claim_policy: str
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if self.contract_version != "platform-profile/1":
            raise ValueError("PLATFORM_PROFILE_INVALID:contract_version")
        if not self.channel_id or not self.rules_version.strip():
            raise ValueError("PLATFORM_PROFILE_INVALID:rules")
        if not isinstance(self.profile_reference, ProfileReference):
            raise TypeError("profile_reference必须是ProfileReference")
        if self.profile_reference.kind is not ProfileKind.CHANNEL:
            raise ValueError("PLATFORM_PROFILE_INVALID:kind")
        if not isinstance(self.fixture_only, bool):
            raise TypeError("fixture_only必须是布尔值")


class PlatformProfileResolver:
    """只展开 S3 ChannelProfile，不联网、不推断平台最新规则。"""

    def resolve(self, profile: ChannelProfile) -> PlatformProfile:
        if not isinstance(profile, ChannelProfile):
            raise TypeError("profile必须是ChannelProfile")
        if not profile.rules_version.strip():
            raise ValueError("PLATFORM_PROFILE_MISSING:rules_version")
        if any(fact.state is not ProfileFactState.CONFIRMED for fact in profile.facts):
            raise ValueError("PLATFORM_PROFILE_INVALID:unconfirmed_fact")
        reference = ProfileReference(
            profile.profile_id,
            ProfileKind.CHANNEL,
            profile.semantic_version,
            tuple(fact.fact_id for fact in profile.facts),
        )
        rules = dict(profile.rules.items)

        def strings(key: str) -> tuple[str, ...]:
            value = rules.get(key, ())
            if not isinstance(value, tuple) or any(
                not isinstance(item, str) for item in value
            ):
                raise ValueError(f"PLATFORM_PROFILE_INVALID:{key}")
            return tuple(item for item in value if isinstance(item, str))

        length_limits = rules.get("length_limits", JsonObject())
        if not isinstance(length_limits, JsonObject):
            raise TypeError("PLATFORM_PROFILE_INVALID:length_limits")
        return PlatformProfile(
            "platform-profile/1",
            reference,
            profile.channel_id,
            profile.rules_version,
            strings("content_structure"),
            strings("tone_rules"),
            length_limits,
            strings("formatting_rules"),
            strings("tag_rules"),
            str(rules.get("factual_claim_policy", "仅允许已有证据")),
            True,
        )


__all__ = ["PlatformProfile", "PlatformProfileResolver"]
