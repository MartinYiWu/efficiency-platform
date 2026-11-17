"""旧可见历史不等于可安全重新注入的历史；血缘未知必须排除。"""

from dataclasses import replace
from time import time

from efficiency_platform_agent.conversation.context import (
    ConversationContext,
    ConversationTurn,
)
from efficiency_platform_agent.core.run_context_binding import (
    RunContextBinding,
    bind_run_context,
)
from tests.integration.context_control.test_memory_execution_mysql import context


def test_unknown_history_is_not_reused_by_memory_enhanced_conversation():
    memory = context()
    history = ConversationContext()
    history.append(ConversationTurn("assistant", "legacy-body-with-unknown-lineage"))
    assert history.provider_messages()
    binding = RunContextBinding(
        memory.packet.scope,
        memory.packet.task_id,
        memory.packet.execution_id,
        int(time()) + 90,
        memory,
    )
    with bind_run_context(binding):
        assert history.turns == ()
        assert history.provider_messages() == ()


def test_history_with_removed_dependency_is_not_reused():
    memory = context()
    source = memory.packet.safety_dependencies[0]
    history = ConversationContext()
    history.append(ConversationTurn("assistant", "answer influenced by A", (source,)))
    binding = RunContextBinding(
        memory.packet.scope,
        memory.packet.task_id,
        memory.packet.execution_id,
        int(time()) + 90,
        memory,
    )
    with bind_run_context(binding):
        assert len(history.turns) == 1
    changed = replace(
        memory, packet=replace(memory.packet, items=(), safety_dependencies=())
    )
    with bind_run_context(replace(binding, memory_context=changed)):
        assert history.turns == ()
