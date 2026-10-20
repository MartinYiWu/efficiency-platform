"""智能客服摄取服务对 API 层暴露的稳定端口。"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from efficiency_platform_agent.agents.customer_service.contracts import (
    IndexVerificationResult,
    IndexVerifyRequest,
    IndexVerifyView,
    IngestJobRequest,
    IngestJobView,
)


class CustomerServiceIngestPort(Protocol):
    async def submit(self, request: IngestJobRequest) -> IngestJobView: ...

    async def get(self, task_id: UUID) -> IngestJobView | None: ...

    async def verify_index(
        self, request: IndexVerifyRequest
    ) -> IndexVerificationResult: ...


__all__ = [
    "CustomerServiceIngestPort",
    "IndexVerifyRequest",
    "IndexVerifyView",
    "IngestJobRequest",
    "IngestJobView",
]
