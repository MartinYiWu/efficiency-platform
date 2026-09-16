from __future__ import annotations

import unittest

from efficiency_platform_agent.agents.operation.specialists.analytics import (
    AnalyticsReviewAgent,
)
from efficiency_platform_agent.agents.operation.specialists.community import (
    CommunityAgent,
)
from efficiency_platform_agent.agents.operation.specialists.user_growth import (
    UserGrowthAgent,
)


class GrowthCommunityAnalyticsTests(unittest.TestCase):
    def test_specialist_ids_and_no_send_tools(self):
        growth, community = UserGrowthAgent(), CommunityAgent()
        self.assertEqual(growth.spec.agent_id, "operation.user_growth.plan")
        self.assertEqual(community.spec.agent_id, "operation.community.plan")
        self.assertFalse(growth.spec.allowed_tools)
        self.assertFalse(community.spec.allowed_tools)

    def test_analytics_agent_is_read_only(self):
        self.assertEqual(
            AnalyticsReviewAgent().spec.agent_id, "operation.analytics.review"
        )
        self.assertFalse(AnalyticsReviewAgent().spec.allowed_tools)


if __name__ == "__main__":
    unittest.main()
