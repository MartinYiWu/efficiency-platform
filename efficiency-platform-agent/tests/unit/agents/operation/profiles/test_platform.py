"""PlatformProfile Resolver 的离线固定规则测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.contracts.profiles import ChannelProfile
from efficiency_platform_agent.agents.operation.profiles.platform import (
    PlatformProfileResolver,
)
from efficiency_platform_agent.core.run import JsonObject


def _channel(rules_version: str = "fixture-1") -> ChannelProfile:
    return ChannelProfile(
        "profile/1",
        "channel-xhs",
        "tenant-a",
        "xiaohongshu",
        rules_version,
        JsonObject(
            (("content_structure", ("title", "body")), ("tone_rules", ("friendly",)))
        ),
        (),
    )


class PlatformProfileTests(unittest.TestCase):
    def test_resolver_expands_confirmed_channel_rules(self) -> None:
        profile = PlatformProfileResolver().resolve(_channel())
        self.assertEqual(profile.channel_id, "xiaohongshu")
        self.assertEqual(profile.rules_version, "fixture-1")
        self.assertTrue(profile.fixture_only)

    def test_resolver_rejects_missing_rules_version(self) -> None:
        with self.assertRaises(ValueError):
            PlatformProfileResolver().resolve(_channel(rules_version=""))


__all__ = ["PlatformProfileTests"]
