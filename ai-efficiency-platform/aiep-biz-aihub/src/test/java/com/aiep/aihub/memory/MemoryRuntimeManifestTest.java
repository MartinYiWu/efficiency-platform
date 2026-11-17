package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryRuntimeManifestTest {
    @Test void controlledActualManifestPreservesBothDependenciesAndRejectsForeignPacketOrAgent() throws Exception {
        var json=new ObjectMapper();var mapper=mock(MemoryPacketMapper.class);var dependencies=mock(MemoryDependencyService.class);
        var scope=new MemoryScopeDTO("t","u","operations","operations","CONVERSATION","s");
        var neutral=new MemoryContextEnvelope.Scope("t","u","operations","operations","CONVERSATION","s");
        var a=new MemoryContextPacket.Dependency("USER_PREFERENCE_DECISION","A","1",0,1,0);
        var b=new MemoryContextPacket.Dependency("USER_PREFERENCE_DECISION","B","1",0,1,0);
        var row=new MemoryPacketMapper.PacketRow("t".getBytes(),"exec".getBytes(),"packet".getBytes(),1,"u".getBytes(),"task".getBytes(),
            json.writeValueAsString(neutral),"{}",json.writeValueAsString(List.of(new MemoryAuthorization.ExecutionGrant("direct","operations","assistant_response"))),
            json.writeValueAsString(java.util.Map.of("input_dependencies",List.of(a))),json.writeValueAsString(List.of(a,b)),"a".repeat(64),"b".repeat(64),"c".repeat(64),"a".repeat(64),"parent".getBytes(),1,0,0,0,600,1,60);
        when(mapper.findPacket(any(),any())).thenReturn(row);
        var service=new MemoryPacketService(true,mock(MemoryMapper.class),mapper,mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),
            mock(MemoryPolicyService.class),mock(MemoryPreferenceService.class),dependencies,mock(MemoryValueCodec.class),mock(PlatformTransactionManager.class),Clock.systemUTC());
        var opScope=new MemoryRuntimeManifest.Scope(neutral,"task","exec","sub","assistant_response","operations");
        var op=new MemoryRuntimeManifest.Operation(opScope,"direct","packet",1,List.of(a,b),List.of(a,b));
        var manifest=new MemoryRuntimeManifest("python-run","exec","packet",1,List.of(op));
        assertEquals(List.of(a,b),service.verifyManifest(scope,"exec","python-run",manifest));
        verify(dependencies).requireCurrent(scope,List.of(a,b));
        assertThrows(RuntimeException.class,()->service.verifyManifest(scope,"exec","other-run",manifest));
        var omitted=new MemoryRuntimeManifest.Operation(opScope,"direct","packet",1,List.of(b),List.of(b));
        assertThrows(RuntimeException.class,()->service.verifyManifest(scope,"exec","python-run",new MemoryRuntimeManifest("python-run","exec","packet",1,List.of(omitted))));
        var forged=new MemoryRuntimeManifest.Operation(new MemoryRuntimeManifest.Scope(neutral,"task","exec","sub","assistant_response","hr"),
            "direct","packet",1,List.of(b),List.of(b));
        assertThrows(RuntimeException.class,()->service.verifyManifest(scope,"exec","python-run",new MemoryRuntimeManifest("python-run","exec","packet",1,List.of(forged))));
    }
}
