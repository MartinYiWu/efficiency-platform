package com.aiep.aihub.memory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MemoryFixtureEndpointTest {
    @Test
    void rejectsNonLocalOrAmbiguousTargetBeforeAnyDispatch() {
        for (String value : new String[] {null, "https://127.0.0.1:8090", "http://example.invalid:8090", "http://user:secret@127.0.0.1:8090", "http://127.0.0.1", "http://127.0.0.1:8090/path", "http://127.0.0.1:8090?token=synthetic", "http://127.0.0.1:8090#fragment"}) {
            var error = assertThrows(IllegalArgumentException.class, () -> OperationContextBusinessIntegrationTest.requireLoopbackFixture(value));
            assertEquals("MEMORY_IT_LOOPBACK_REQUIRED", error.getMessage());
        }
        assertEquals("127.0.0.1", OperationContextBusinessIntegrationTest.requireLoopbackFixture("http://127.0.0.1:53123").getHost());
    }
}
