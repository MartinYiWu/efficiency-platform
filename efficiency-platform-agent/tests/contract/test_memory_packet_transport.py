"""Java 与 Python 使用同一完整包与规范摘要金样本。"""

import json
from pathlib import Path

from efficiency_platform_agent.contracts.memory import MemoryContextPacketModel
from efficiency_platform_agent.contracts.memory_context import MemoryContextEnvelope
from efficiency_platform_agent.security.memory_packet import (
    memory_packet_digest,
    memory_packet_semantic_digest,
)


def test_java_packet_fixture_has_identical_digests():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/memory_packet_transport.json").read_text(
            encoding="utf-8"
        )
    )
    model = MemoryContextPacketModel.model_validate_json(json.dumps(fixture["packet"]))
    assert model.model_dump(mode="json") == fixture["packet"]
    assert memory_packet_digest(model.to_core()) == fixture["packet_digest"]
    assert memory_packet_semantic_digest(model.to_core()) == fixture["semantic_digest"]
    envelope = MemoryContextEnvelope.model_validate_json(
        json.dumps(fixture["envelope"])
    )
    assert envelope.to_core().input_dependencies
    assert (
        envelope.model_dump(mode="json")["authorization"]["input_dependencies"]
        == fixture["envelope"]["authorization"]["input_dependencies"]
    )
