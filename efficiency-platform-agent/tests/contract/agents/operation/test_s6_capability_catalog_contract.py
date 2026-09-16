from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
    operation_agent_specs,
    operation_capability_specs,
    operation_specialist_capability_ids,
)


def test_s6_uses_canonical_operation_capability_catalog():
    values = tuple(item.value for item in OperationSpecialistCapabilityId)
    assert operation_specialist_capability_ids() == values
    assert len(values) == 11


def test_capability_and_agent_specs_have_one_to_one_catalog_ownership():
    values = operation_specialist_capability_ids()
    capability_specs = operation_capability_specs()
    agent_specs = operation_agent_specs()
    assert tuple(item.capability_id for item in capability_specs) == values
    assert len(agent_specs) == len(values)
    assert all(len(spec.capability_ids) == 1 for spec in agent_specs)
    assert {
        capability_id for spec in agent_specs for capability_id in spec.capability_ids
    } == set(values)
