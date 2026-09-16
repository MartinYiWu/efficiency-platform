"""S5C 内容、渠道、活动 Specialist 的离线身份和边界测试。"""

from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.specialists.campaign import (
    CampaignOperationAgent,
)
from efficiency_platform_agent.agents.operation.specialists.channel import (
    ChannelContentAgent,
)
from efficiency_platform_agent.agents.operation.specialists.content import ContentAgent


class ContentChannelCampaignSpecialistTests(unittest.TestCase):
    def test_three_specialists_have_distinct_ids_and_no_write_capability(self) -> None:
        agents = (ContentAgent(), ChannelContentAgent(), CampaignOperationAgent())
        self.assertEqual(
            tuple(agent.spec.agent_id for agent in agents),
            (
                "operation.content.create",
                "operation.channel.content",
                "operation.campaign.plan",
            ),
        )
        for agent in agents:
            self.assertEqual(agent.spec.allowed_tools, frozenset())
            self.assertEqual(agent.spec.permissions, frozenset())


__all__ = ["ContentChannelCampaignSpecialistTests"]
