from efficiency_platform_agent.core.memory_execution import (
    memory_operation_deadline_matches,
)


def test_only_derive_may_shorten_and_nobody_may_extend_original_deadline():
    assert memory_operation_deadline_matches("memory.derive", 99, 100)
    assert memory_operation_deadline_matches("memory.derive", 100, 100)
    assert not memory_operation_deadline_matches("memory.derive", 101, 100)
    assert not memory_operation_deadline_matches("memory.derive", 0, 100)
    assert not memory_operation_deadline_matches("memory.derive", True, 100)
    assert not memory_operation_deadline_matches("direct", 99, 100)
    assert memory_operation_deadline_matches("direct", 100, 100)
