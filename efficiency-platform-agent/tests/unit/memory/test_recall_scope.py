import time
from dataclasses import replace

import pytest

from efficiency_platform_agent.core.memory import ConversationScope, ExecutionScope
from efficiency_platform_agent.core.memory_index import (
    MemoryIndexIdentity,
    MemoryIndexScope,
    MemoryIndexSpace,
    MemoryRecallCandidate,
)
from efficiency_platform_agent.memory.recall import (
    AuthorizedMemoryRecall,
    MemoryRecallService,
)


def request():
    scope = ConversationScope("t", "u", "operations", "operations", "CONVERSATION", "s")
    item = MemoryIndexIdentity("item", "v1", 1, 0, "a" * 64)
    return AuthorizedMemoryRecall(
        MemoryIndexScope("t", "u", "operations", "operations"),
        MemoryIndexSpace("model", 3, "policy/1"),
        ExecutionScope(scope, "task", "execution", "node", "ANSWER", "operations"),
        (item,),
        int(time.time()) + 30,
    )


class Authority:
    def __init__(self):
        self.checks = 0
        self.revoked = False

    async def check(self, request):
        self.checks += 1
        if self.revoked:
            raise ValueError("MEMORY_ACCESS_REVOKED")


class Index:
    def __init__(self, items, authority=None):
        self.items, self.authority = items, authority
        self.calls = 0

    async def search(self, scope, space, allowed, *, vector, terms, limit):
        self.calls += 1
        assert limit == 30
        if self.authority:
            self.authority.revoked = True
        return (), self.items


@pytest.mark.asyncio
async def test_exact_legal_set_shortfall_does_not_expand_scope_or_embed():
    authorized = request()
    index = Index((MemoryRecallCandidate(authorized.allowed[0], 1.0),))
    result = await MemoryRecallService(index, Authority(), enabled=True).recall(
        authorized, terms=("language",)
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].identity == authorized.allowed[0]
    assert result.query_embedding_status == "NOT_REQUESTED"
    assert result.hydration_required is True
    assert index.calls == 1
    empty = await MemoryRecallService(index, Authority(), enabled=True).recall(
        replace(authorized, allowed=()), query="never sent"
    )
    assert empty.candidates == ()
    assert index.calls == 1


@pytest.mark.asyncio
async def test_wrong_version_and_revocation_during_recall_return_no_candidates():
    authorized = request()
    wrong = replace(authorized.allowed[0], version_id="other")
    with pytest.raises(ValueError, match="MEMORY_RECALL_SCOPE_DENIED"):
        await MemoryRecallService(
            Index((MemoryRecallCandidate(wrong, 1.0),)), Authority(), enabled=True
        ).recall(authorized)
    authority = Authority()
    with pytest.raises(ValueError, match="MEMORY_ACCESS_REVOKED"):
        await MemoryRecallService(
            Index((MemoryRecallCandidate(authorized.allowed[0], 1.0),), authority),
            authority,
            enabled=True,
        ).recall(authorized)


def test_same_user_cross_agent_and_generation_are_not_interchangeable():
    authorized = request()
    assert (
        authorized.scope.key
        != MemoryIndexScope("t", "u", "customer-service", "customer-service").key
    )
    with pytest.raises(ValueError, match="MEMORY_RECALL_AUTHORIZATION_INVALID"):
        replace(
            authorized, scope=MemoryIndexScope("t", "other", "operations", "operations")
        )
