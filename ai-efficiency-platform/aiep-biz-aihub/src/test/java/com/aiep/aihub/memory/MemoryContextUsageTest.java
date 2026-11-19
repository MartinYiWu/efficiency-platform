package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.operation.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemoryRuntimeManifest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryContextUsageTest {
    @SuppressWarnings("unchecked")
    private MemoryContextUsageService service(MemoryScopePolicy scopes,MemoryPacketService packets,
            OperationRunMapper runs,AiInvokeFacade ai) {
        var summaries=(ObjectProvider<MemorySummaryService>)mock(ObjectProvider.class);
        return new MemoryContextUsageService(scopes,mock(MemorySessionBindingService.class),packets,
            runs,mock(CustomerServiceMappers.class),ai,summaries);
    }
    private MemoryScopePolicy scopes() {
        var scopes=mock(MemoryScopePolicy.class);
        when(scopes.currentActor()).thenReturn(new IdentityFacade.Subject("tenant","user",java.util.Set.of(),java.util.Set.of(),java.util.Set.of(),java.util.Set.of(),List.of(),"login"));
        return scopes;
    }
    @Test void readWithoutRunNeverGeneratesOrCallsAgent() {
        var ai=mock(AiInvokeFacade.class);var runs=mock(OperationRunMapper.class);
        var result=service(scopes(),mock(MemoryPacketService.class),runs,ai).read("operations","session",null);
        assertEquals("EMPTY",result.status());assertTrue(result.operations().isEmpty());verifyNoInteractions(ai,runs);
    }
    @Test void runFromAnotherConversationCannotReadManifest() {
        var ai=mock(AiInvokeFacade.class);var runs=mock(OperationRunMapper.class);
        var run=new OperationRunPO();run.setTenantId("tenant");run.setConversationId("other");run.setAgentRunId("runtime");when(runs.selectById("run")).thenReturn(run);
        assertThrows(MemoryException.class,()->service(scopes(),mock(MemoryPacketService.class),runs,ai).read("operations","session","run"));
        verifyNoInteractions(ai);
    }
    @Test void manifestMetricsPreserveMissingVersusMeasuredValues() throws Exception {
        var json=new ObjectMapper();
        var old=json.readValue("{\"scope\":null,\"node_id\":\"direct\",\"packet_id\":\"packet\",\"packet_revision\":1,\"safety_dependencies\":[],\"selected_sources\":[]}",MemoryRuntimeManifest.Operation.class);
        assertNull(old.measurement());assertNull(old.cpuBeforeTokens());
        var measured=json.readValue("{\"scope\":null,\"node_id\":\"direct\",\"packet_id\":\"packet\",\"packet_revision\":1,\"safety_dependencies\":[],\"selected_sources\":[],\"measurement\":{\"total_upper_bound\":480,\"method\":\"counter/1\",\"verified\":true},\"decision\":{\"H_ctx\":2000,\"T\":480,\"F\":1520,\"status\":\"ALLOW\"},\"cpu_before_tokens\":700}",MemoryRuntimeManifest.Operation.class);
        assertEquals(480L,measured.measurement().totalUpperBound());assertEquals(2000L,measured.decision().inputLimit());assertEquals(700L,measured.cpuBeforeTokens());
    }
}
