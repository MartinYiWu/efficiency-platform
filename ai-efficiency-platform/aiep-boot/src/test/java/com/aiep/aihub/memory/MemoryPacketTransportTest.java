package com.aiep.aihub.memory;

import com.aiep.platformai.api.dto.MemoryContextPacket;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MemoryPacketTransportTest {
    @Test void pythonFixtureHasIdenticalCompleteAndSemanticDigest() throws Exception {
        var json = new ObjectMapper();
        var fixture = json.readTree(Files.readString(Path.of("../../efficiency-platform-agent/tests/fixtures/memory_packet_transport.json")));
        var packet = json.treeToValue(fixture.get("packet"), MemoryContextPacket.class);
        assertEquals(fixture.get("packet_digest").asText(), MemoryPacketDigest.digest(packet));
        assertEquals(fixture.get("semantic_digest").asText(), MemoryPacketDigest.semanticDigest(packet));
        assertEquals(fixture.get("packet"), json.readTree(json.writeValueAsString(packet)));
        var envelope=json.treeToValue(fixture.get("envelope"),com.aiep.platformai.api.dto.MemoryContextEnvelope.class);
        assertFalse(envelope.authorization().inputDependencies().isEmpty());
        assertEquals(fixture.get("envelope").path("authorization").path("input_dependencies"),
            json.readTree(json.writeValueAsString(envelope)).path("authorization").path("input_dependencies"));
    }
}
