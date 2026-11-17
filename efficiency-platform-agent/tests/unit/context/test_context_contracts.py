from dataclasses import replace

import pytest
from pydantic import ValidationError

from efficiency_platform_agent.agents.validation import AgentValidator
from efficiency_platform_agent.contracts.context_control import WindowLimitsModel
from efficiency_platform_agent.core.context_control import (
    ModelCapacity,
    TokenMeasurement,
    WindowLimits,
)
from efficiency_platform_agent.core.memory import MemoryContextPacket, MemoryPolicy
from tests.support.agent_fakes import build_synthetic_spec
from tests.unit.memory.test_scope_contracts import scope


def test_window_limits_strict_nonnegative_and_roundtrip():
    limits = WindowLimits(1000, 900, 100, 50, 800)
    assert limits.input_cap() == 800
    assert WindowLimitsModel.from_core(limits).to_core() == limits
    for invalid in (-1, True, "100"):
        with pytest.raises((ValueError, TypeError)):
            replace(limits, node_input_limit=invalid)
        with pytest.raises(ValidationError):
            WindowLimitsModel(
                **{
                    **WindowLimitsModel.from_core(limits).model_dump(),
                    "node_input_limit": invalid,
                }
            )


def test_capacity_and_measurement_validate():
    capacity = ModelCapacity(
        "provider",
        "model",
        "v1",
        1000,
        None,
        200,
        "tokenizer",
        "serialization",
        "included",
        True,
        "evidence",
    )
    with pytest.raises(ValueError):
        replace(capacity, verified=1)
    measurement = TokenMeasurement(10, (("messages", 10),), "exact", True)
    for invalid in (-1, True):
        with pytest.raises(ValueError):
            replace(measurement, total_upper_bound=invalid)
    with pytest.raises(ValueError):
        replace(measurement, by_component=(("messages", -1),))


def test_unknown_memory_policy_is_disabled_and_known_is_limited():
    spec = build_synthetic_spec()
    validator = AgentValidator()
    validator.validate_spec(spec)
    assert validator.validate_memory_policy(spec, {}).enabled is False
    policy = MemoryPolicy(
        policy_id=spec.memory_policy_id,
        version="1",
        domain="operations",
        agent_ids=frozenset({spec.agent_id}),
    )
    assert validator.validate_memory_policy(spec, {policy.policy_id: policy}) == policy
    assert (
        validator.validate_memory_policy(
            spec, {policy.policy_id: replace(policy, agent_ids=frozenset({"other"}))}
        ).enabled
        is False
    )


def test_packet_scope_mismatch_rejects():
    packet = MemoryContextPacket(
        packet_id="packet",
        packet_revision=1,
        scope=scope(),
        task_id="task",
        execution_id="execution",
        policy_version="1",
        execution_revision=1,
        issued_at=1,
        expires_at=61,
        grant_epoch=0,
        source_epoch=0,
        deletion_epoch=0,
        semantic_input_hash="hash",
        parent_authorization_ref="auth",
    )
    packet.validate_scope(scope(), "task", "execution")
    with pytest.raises(ValueError, match="PACKET_SCOPE_MISMATCH"):
        packet.validate_scope(replace(scope(), user_id="other"), "task", "execution")


def test_core_contracts_have_no_upper_layer_or_framework_imports():
    import ast
    from pathlib import Path

    package = Path(__file__).resolve().parents[3] / "src/efficiency_platform_agent/core"
    for name in ("context_control.py", "memory.py", "memory_ports.py"):
        tree = ast.parse((package / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 1 or node.module.split(".")[0] in {
                    "__future__",
                    "dataclasses",
                    "typing",
                }
            elif isinstance(node, ast.Import):
                pytest.fail("核心合同不需要额外运行时依赖")


def test_all_context_boundary_models_roundtrip():
    from efficiency_platform_agent.contracts import context_control as boundary
    from efficiency_platform_agent.core import context_control as core
    from efficiency_platform_agent.core.memory import ExecutionScope, SourceDependency

    capacity = ModelCapacity(
        "provider",
        "model",
        "1",
        1000,
        None,
        200,
        "conservative-utf8/1",
        "openai-chat/1",
        "NO_REASONING",
        True,
        "evidence",
    )
    measurement = TokenMeasurement(100, (("messages", 100),), "upper-bound", True)
    decision = core.WindowDecision(800, 100, 50, "ALLOW")
    dep = SourceDependency("message", "source", "1")
    manifest = core.ContextManifest(
        "manifest",
        ExecutionScope(
            scope(), "task", "execution", "subtask", "answer", "general_chat"
        ),
        "operation",
        "node",
        1,
        "1",
        "1",
        "1",
        "1",
        "tokenizer",
        "serialization",
        "1",
        None,
        None,
        1,
        (dep,),
        (dep,),
        (),
        measurement,
        decision,
        100,
        50,
        "hmac",
    )
    for value in (
        capacity,
        WindowLimits(1000, None, 100, 50, 800),
        measurement,
        decision,
        manifest,
    ):
        schema = getattr(boundary, type(value).__name__ + "Model")
        assert schema.from_core(value).to_core() == value
    with pytest.raises(ValueError, match="MANIFEST_DEPENDENCIES_INCOMPLETE"):
        replace(manifest, safety_dependencies=())


def test_packet_boundary_roundtrip_and_dependency_closure():
    from efficiency_platform_agent.contracts.memory import MemoryContextPacketModel
    from efficiency_platform_agent.core.memory import MemoryReference, SourceDependency

    dep = SourceDependency("message", "message-id", "1")
    item = MemoryReference("item", "1", "response.language", "zh", (dep,))
    packet = MemoryContextPacket(
        "packet",
        1,
        scope(),
        "task",
        "execution",
        "1",
        1,
        1,
        61,
        0,
        0,
        0,
        "hash",
        "auth",
        (item,),
        (dep,),
    )
    assert MemoryContextPacketModel.from_core(packet).to_core() == packet
    for field in ("task_id", "execution_id"):
        with pytest.raises(ValueError, match="PACKET_SCOPE_MISMATCH"):
            packet.validate_scope(
                scope(),
                "other" if field == "task_id" else "task",
                "other" if field == "execution_id" else "execution",
            )
    with pytest.raises(ValueError, match="PACKET_DEPENDENCIES_INCOMPLETE"):
        replace(packet, safety_dependencies=())
