"""S5D 用户增长、社群和分析复盘的离线验收。"""

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
from efficiency_platform_agent.capabilities.analytics.contracts import (
    AnalyticsDatasetReference,
    AnalyticsFileFormat,
    AnalyticsFileReadRequest,
)
from tests.support.analytics_fixture_reader import FixtureAnalyticsFileReader


class OperationGrowthCommunityAnalyticsAcceptanceTests(
    unittest.IsolatedAsyncioTestCase
):
    """验证固定数据可复核且 Specialist 不产生外部触达。"""

    @staticmethod
    def _request() -> AnalyticsFileReadRequest:
        return AnalyticsFileReadRequest(
            AnalyticsDatasetReference(
                "analytics-dataset-reference/1",
                "dataset-1",
                "tenant-1",
                AnalyticsFileFormat.CSV,
                "operation_metrics_v1.csv",
                "operation-metrics/1",
            ),
            None,
            ("date", "channel", "visits", "activations"),
            10,
            4,
            100_000,
        )

    async def test_analytics_recomputes_fixture_totals_and_releases_lease(self) -> None:
        reader = FixtureAnalyticsFileReader()
        summary = await AnalyticsReviewAgent(reader).summarize(self._request())
        self.assertEqual(summary["dataset_id"], "dataset-1")
        self.assertEqual(summary["totals"]["visits"], 600)
        self.assertEqual(summary["totals"]["activations"], 120)
        self.assertEqual(summary["causality"], "hypothesis")
        self.assertEqual((reader.open_count, reader.close_count), (1, 1))
        self.assertIsNone(reader.active_dataset)

    def test_growth_and_community_are_plan_only(self) -> None:
        growth, community, analytics = (
            UserGrowthAgent(),
            CommunityAgent(),
            AnalyticsReviewAgent(),
        )
        self.assertEqual(growth.spec.allowed_tools, frozenset())
        self.assertEqual(community.spec.allowed_tools, frozenset())
        self.assertEqual(analytics.spec.allowed_tools, frozenset())
        self.assertEqual(growth.spec.permissions, frozenset())
        self.assertEqual(community.spec.permissions, frozenset())


__all__ = ["OperationGrowthCommunityAnalyticsAcceptanceTests"]
