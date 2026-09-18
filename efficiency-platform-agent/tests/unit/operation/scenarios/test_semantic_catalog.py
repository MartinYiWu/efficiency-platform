"""I05 真实运营能力的语义目录投影测试。"""

from efficiency_platform_agent.agents.operation.definition import (
    OperationSpecialistCapabilityId,
)
from efficiency_platform_agent.agents.operation.scenarios.semantic_catalog import (
    build_operation_semantic_catalog,
    build_operation_semantic_registry_view,
    build_semantic_catalog,
)


def test_semantic_catalog_is_one_to_one_projection_of_real_capabilities() -> None:
    catalog = build_operation_semantic_catalog()

    assert tuple(item.capability_id for item in catalog.capabilities) == tuple(
        sorted(item.value for item in OperationSpecialistCapabilityId)
    )
    assert all(item.description.strip() for item in catalog.capabilities)
    assert all(item.positive_examples for item in catalog.capabilities)
    assert all(item.negative_examples for item in catalog.capabilities)
    assert all(item.parameter_schema_ref for item in catalog.capabilities)


def test_catalog_version_is_deterministic_and_manifest_outputs_are_projected() -> None:
    view = build_operation_semantic_registry_view()
    first = build_semantic_catalog(view)
    second = build_semantic_catalog(view)

    assert first == second
    assert first.catalog_version.startswith("operation-semantic/")
    research = next(
        item
        for item in first.capabilities
        if item.capability_id == "operation.research.insight"
    )
    assert "industry-report" in research.supported_outputs
    assert research.required_permissions == ("synthetic.read",)


def test_semantic_view_reuses_real_schema_and_agent_versions() -> None:
    view = build_operation_semantic_registry_view()
    catalog = build_semantic_catalog(view)
    capabilities = {item.capability_id: item for item in view.capabilities}
    agents = {
        capability_id: agent
        for agent in view.agents
        for capability_id in agent.capability_ids
    }

    for descriptor in catalog.capabilities:
        assert descriptor.version == capabilities[descriptor.capability_id].semantic_version
        assert descriptor.capability_id in agents
        assert descriptor.parameter_schema_ref.startswith(
            "operation-intent-parameters/"
        )
