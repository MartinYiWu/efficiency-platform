"""R03 Provider 契约测试支持对象。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

from efficiency_platform_agent.contracts.research_sources_v2 import (
    FetchedContentV2,
    FetchRequestV2,
)


class FakeDocumentFetcher:
    def __init__(
        self,
        responses: Mapping[str, FetchedContentV2 | Exception],
        *,
        delay_seconds: float = 0.0,
    ) -> None:
        self.responses = dict(responses)
        self.requests: list[FetchRequestV2] = []
        self.active = 0
        self.max_active = 0
        self.delay_seconds = delay_seconds

    async def fetch(self, request: FetchRequestV2) -> FetchedContentV2:
        self.requests.append(request)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            result = self.responses[request.url]
            if isinstance(result, Exception):
                raise result
            return result.model_copy(
                update={
                    "request_id": request.request_id,
                    "candidate_id": request.candidate_id,
                }
            )
        finally:
            self.active -= 1


def fetched(
    *,
    url: str,
    body: bytes,
    media_type: str,
    status_code: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
) -> FetchedContentV2:
    return FetchedContentV2(
        request_id="fixture-fetch",
        candidate_id="fixture-document",
        final_url=url,
        media_type=media_type,
        body=body,
        downloaded_bytes=len(body),
        fetched_at=datetime(2026, 9, 16, 12, tzinfo=UTC),
        status_code=status_code,
        response_headers=headers,
    )
