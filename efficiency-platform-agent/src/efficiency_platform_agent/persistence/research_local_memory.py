"""单进程本地研究事实库；重启不恢复，活动引用不被容量清理驱逐。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from efficiency_platform_agent.contracts.research_local_runtime_v2 import (
    LocalResearchRunFactsV2,
    LocalResearchRunKeyV2,
)
from efficiency_platform_agent.contracts.research_v2 import (
    ResearchBriefV2,
    ResearchOutcomeV2,
)


@dataclass(slots=True)
class _Entry:
    facts: LocalResearchRunFactsV2
    references: int = 0


class LocalResearchRunStore:
    def __init__(
        self,
        *,
        ttl: timedelta = timedelta(minutes=30),
        max_runs: int = 100,
        max_run_bytes: int = 20 * 1024 * 1024,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if (
            not timedelta(0) < ttl <= timedelta(minutes=30)
            or not 0 < max_runs <= 100
            or not 0 < max_run_bytes <= 20 * 1024 * 1024
        ):
            raise ValueError("LOCAL_RESEARCH_LIMIT_INVALID")
        self.ttl, self.max_runs, self.max_run_bytes, self.now = (
            ttl,
            max_runs,
            max_run_bytes,
            now,
        )
        self._entries: dict[LocalResearchRunKeyV2, _Entry] = {}
        self._lock = asyncio.Lock()

    async def create(self, key: LocalResearchRunKeyV2, brief: ResearchBriefV2) -> None:
        async with self._lock:
            self._expire(self.now())
            existing = self._entries.get(key)
            if existing is not None:
                if existing.facts.brief != brief:
                    raise ValueError("LOCAL_RESEARCH_BRIEF_CONFLICT")
                return
            if len(self._entries) >= self.max_runs:
                raise ValueError("LOCAL_RESEARCH_CAPACITY")
            now = self.now()
            facts = self._validate(
                LocalResearchRunFactsV2(
                    key=key, brief=brief, created_at=now, expires_at=now + self.ttl
                )
            )
            self._entries[key] = _Entry(facts)

    async def get(self, key: LocalResearchRunKeyV2) -> LocalResearchRunFactsV2:
        async with self._lock:
            self._expire(self.now())
            return self._entries[key].facts.model_copy(deep=True)

    async def put(
        self, key: LocalResearchRunKeyV2, facts: LocalResearchRunFactsV2
    ) -> None:
        async with self._lock:
            self._expire(self.now())
            entry = self._entries[key]
            old = entry.facts
            if old.status != "active":
                raise ValueError("LOCAL_RESEARCH_TERMINAL")
            if (
                facts.key != key
                or facts.brief != old.brief
                or facts.created_at != old.created_at
                or facts.expires_at != old.expires_at
                or facts.status != old.status
                or facts.outcome != old.outcome
            ):
                raise ValueError("LOCAL_RESEARCH_FACTS_CONFLICT")
            if facts.version != old.version:
                raise ValueError("LOCAL_RESEARCH_VERSION_CONFLICT")
            entry.facts = self._validate(
                facts.model_copy(update={"version": old.version + 1})
            )

    async def finish(
        self,
        key: LocalResearchRunKeyV2,
        *,
        status: Literal["completed", "failed", "cancelled", "timed_out"],
        outcome: ResearchOutcomeV2 | None = None,
    ) -> None:
        async with self._lock:
            entry = self._entries[key]
            if entry.facts.status != "active":
                if entry.facts.status != status or entry.facts.outcome != outcome:
                    raise ValueError("LOCAL_RESEARCH_TERMINAL_CONFLICT")
                return
            facts = entry.facts.model_copy(
                update={
                    "status": status,
                    "outcome": outcome,
                    "version": entry.facts.version + 1,
                    "expires_at": self.now() + self.ttl,
                    "documents": {},
                    "extracted_documents": {},
                    "candidates": {},
                    "drafts": {},
                }
            )
            entry.facts = self._validate(facts)

    @asynccontextmanager
    async def reference(self, key: LocalResearchRunKeyV2) -> AsyncIterator[None]:
        async with self._lock:
            self._expire(self.now())
            entry = self._entries[key]
            entry.references += 1
        try:
            yield
        finally:
            async with self._lock:
                entry.references -= 1

    async def expire(self, now: datetime) -> int:
        async with self._lock:
            return self._expire(now)

    async def retained_keys(self) -> frozenset[LocalResearchRunKeyV2]:
        async with self._lock:
            self._expire(self.now())
            return frozenset(self._entries)

    def _expire(self, now: datetime) -> int:
        expired = [
            key
            for key, entry in self._entries.items()
            if entry.references == 0 and entry.facts.expires_at <= now
        ]
        for key in expired:
            del self._entries[key]
        return len(expired)

    def _validate(self, facts: LocalResearchRunFactsV2) -> LocalResearchRunFactsV2:
        validated = LocalResearchRunFactsV2.model_validate(
            facts.model_dump(mode="python", warnings=False)
        )
        if len(validated.model_dump_json().encode("utf-8")) > self.max_run_bytes:
            raise ValueError("LOCAL_RESEARCH_RUN_SIZE")
        return validated.model_copy(deep=True)
