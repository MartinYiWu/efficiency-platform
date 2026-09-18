"""本地事实库的身份、保留和并发更新契约；不连接数据库。"""

import asyncio
import importlib
from datetime import UTC, datetime, timedelta

import pytest

from tests.unit.capabilities.research_v2._delivery_support import delivery_facts

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def local_types():
    name = "efficiency_platform_agent.persistence.research_local_memory"
    assert importlib.util.find_spec(name), "Task3 缺少本地事实库"
    memory = importlib.import_module(name)
    contracts = importlib.import_module(
        "efficiency_platform_agent.contracts.research_local_runtime_v2"
    )
    return memory.LocalResearchRunStore, contracts.LocalResearchRunKeyV2


def case(*, tenant="t", user="u", conversation="c", run="r", revision=1):
    _, key_type = local_types()
    brief, *_ = delivery_facts()
    brief = brief.model_copy(
        update={
            "trusted_context": brief.trusted_context.model_copy(
                update={
                    "tenant_id": tenant,
                    "run_id": run,
                    "budget_lease_id": f"lease-{run}",
                }
            ),
            "intent_revision": revision,
        }
    )
    return key_type(
        tenant_id=tenant,
        user_id=user,
        conversation_id=conversation,
        run_id=run,
        task_id="x",
        revision=revision,
    ), brief


@pytest.mark.parametrize(
    "dimension",
    ["tenant_id", "user_id", "conversation_id", "run_id", "task_id", "revision"],
)
async def test_foreign_identity_cannot_read_or_replace_facts(dimension):
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    key, brief = case()
    await store.create(key, brief)
    foreign = key.model_copy(
        update={dimension: 2 if dimension == "revision" else "foreign"}
    )
    with pytest.raises(KeyError):
        await store.get(foreign)
    with pytest.raises((KeyError, ValueError)):
        await store.put(foreign, await store.get(key))


async def test_concurrent_create_retry_is_idempotent_and_does_not_share_mutable_facts():
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    pairs = [case(tenant=f"t{i}", user=f"u{i}", run=f"r{i}") for i in range(2)]
    await asyncio.gather(
        *(store.create(key, brief) for key, brief in pairs for _ in range(2))
    )
    for key, brief in pairs:
        facts = await store.get(key)
        assert facts.brief == brief
        facts.stage_artifact_ids["discover"] = ("foreign-change",)
        assert not (await store.get(key)).stage_artifact_ids


async def test_cas_prevents_two_writers_from_losing_an_update():
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    key, brief = case()
    await store.create(key, brief)
    facts = await store.get(key)
    results = await asyncio.gather(
        store.put(key, facts), store.put(key, facts), return_exceptions=True
    )
    assert sum(result is None for result in results) == 1
    assert any(isinstance(result, ValueError) for result in results)
    assert (await store.get(key)).version == 1


async def test_ttl_capacity_never_evicts_active_references():
    store_type, _ = local_types()
    clock = [NOW]
    store = store_type(now=lambda: clock[0], max_runs=1)
    key, brief = case()
    await store.create(key, brief)
    other, other_brief = case(run="other")
    async with store.reference(key):
        clock[0] += timedelta(minutes=31)
        assert await store.expire(clock[0]) == 0
        with pytest.raises(ValueError, match="CAPACITY"):
            await store.create(other, other_brief)
        assert (await store.get(key)).brief == brief
    assert await store.expire(clock[0]) == 1
    with pytest.raises(KeyError):
        await store.get(key)
    await store.create(other, other_brief)


async def test_run_size_limit_and_brief_conflict_do_not_corrupt_existing_facts():
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW, max_run_bytes=4096)
    key, brief = case()
    await store.create(key, brief)
    with pytest.raises(ValueError, match="CONFLICT"):
        await store.create(key, brief.model_copy(update={"topic": "other"}))
    facts = await store.get(key)
    facts.stage_artifact_ids["discover"] = tuple(f"artifact-{i}" for i in range(1000))
    with pytest.raises(ValueError, match="SIZE"):
        await store.put(key, facts)
    assert (await store.get(key)).version == 0


async def test_terminal_releases_documents_but_retains_outcome_until_ttl():
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    key, brief = case()
    await store.create(key, brief)
    _, _, document, *_ = delivery_facts()
    facts = await store.get(key)
    facts.documents[document.document_id] = document
    await store.put(key, facts)
    await store.finish(key, status="cancelled")
    terminal = await store.get(key)
    assert terminal.status == "cancelled"
    assert terminal.documents == {}
    with pytest.raises(ValueError, match="TERMINAL"):
        await store.put(key, terminal)


async def test_typed_facts_reject_invalid_payload_even_when_model_copy_skips_validation():
    store_type, _ = local_types()
    store = store_type(now=lambda: NOW)
    key, brief = case()
    await store.create(key, brief)
    facts = (await store.get(key)).model_copy(
        update={"documents": {"bad": {"text": "untyped"}}}
    )
    with pytest.raises(ValueError):
        await store.put(key, facts)
