"""S5C 内容、渠道和活动 Specialist 的固定样本验收。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from efficiency_platform_agent.agents.operation.specialists.campaign import (
    CampaignOperationAgent,
)
from efficiency_platform_agent.agents.operation.specialists.channel import (
    ChannelContentAgent,
)
from efficiency_platform_agent.agents.operation.specialists.content import ContentAgent


class OperationContentChannelCampaignAcceptanceTests(unittest.TestCase):
    def test_content_channel_campaign_have_independent_outputs(self) -> None:
        root = Path(__file__).parents[1] / "fixtures" / "operation"
        expected = (
            json.loads(
                (root / "content" / "content_calendar_v1.json").read_text(
                    encoding="utf-8"
                )
            )["expected_kind"],
            "channel_content",
            json.loads(
                (root / "campaign" / "online_acquisition_v1.json").read_text(
                    encoding="utf-8"
                )
            )["expected_kind"],
        )
        agents = (ContentAgent(), ChannelContentAgent(), CampaignOperationAgent())
        labels = []
        for agent in agents:
            result = agent.build_result(
                SimpleNamespace(task_id=agent.spec.agent_id, operation_context=None)
            )
            assert result.deliverable_bundle is not None
            labels.append(
                dict(result.deliverable_bundle.deliverables[0].payload.items)[
                    "deliverable_kind"
                ]
            )
        self.assertEqual(tuple(labels), expected)
        self.assertEqual(len(set(labels)), 3)


__all__ = ["OperationContentChannelCampaignAcceptanceTests"]
