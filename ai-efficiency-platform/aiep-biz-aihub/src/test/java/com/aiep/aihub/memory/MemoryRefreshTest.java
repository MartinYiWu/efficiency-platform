package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.TransactionDefinition;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryRefreshTest {
    final MemoryRefreshMapper refresh=mock(MemoryRefreshMapper.class);
    final MemoryPacketMapper packets=mock(MemoryPacketMapper.class);
    final IdentityFacade identity=mock(IdentityFacade.class);
    final MemoryScopeDTO scope=new MemoryScopeDTO("t","u","operations","operations","TASK_ONLY",null);
    final MemoryContextWait wait=new MemoryContextWait("memory-context-wait/1","w","runtime","task","e",
        new MemoryContextEnvelope.Scope("t","u","operations","operations","TASK_ONLY",null),1,1,"a".repeat(64),
        "b".repeat(64),"op","c".repeat(64),null,1,null,null,MemoryContextWait.CheckpointMode.NONE,null,null,
        MemoryContextWait.WaitPhase.BEFORE_PREPARE,1200,0);
    final IdentityFacade.Subject actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"old-login");
    MemoryPacketService service() {
        var tx=new AbstractPlatformTransactionManager() {
            protected Object doGetTransaction(){return new Object();}
            protected void doBegin(Object t,TransactionDefinition d){}
            protected void doCommit(DefaultTransactionStatus s){}
            protected void doRollback(DefaultTransactionStatus s){}
        };
        return new MemoryPacketService(true,mock(MemoryMapper.class),packets,mock(MemoryScopePolicy.class),
            mock(MemorySessionBindingService.class),mock(MemoryPolicyService.class),mock(MemoryPreferenceService.class),
            mock(MemoryDependencyService.class),mock(MemoryValueCodec.class),tx,Clock.fixed(Instant.ofEpochSecond(1000),ZoneOffset.UTC),true,refresh,identity);
    }
    MemoryRefreshMapper.Anchor anchor(){return new MemoryRefreshMapper.Anchor(b("t"),b("e"),b("u"),b("packet"),1,1,"d".repeat(64),"f".repeat(64),1200,b("old-login"),60,1300);}
    @Test void missingAnchorNeverBorrowsCurrentLogin() {
        var failure=assertThrows(MemoryContracts.MemoryException.class,()->service().prepareRefresh(scope,wait,"r"));
        assertEquals("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED",failure.code());verifyNoInteractions(identity);verify(refresh,never()).insertCandidate(any(),any());
    }
    @Test void revokedOriginalLoginCannotUseAnotherValidLogin() {
        when(refresh.findAnchor(any(),any())).thenReturn(anchor());
        when(identity.refresh("t","u","old-login")).thenReturn(Optional.empty());
        when(identity.refresh("t","u")).thenReturn(Optional.of(actor));
        assertEquals("ACCESS_REVOKED",assertThrows(MemoryContracts.MemoryException.class,()->service().prepareRefresh(scope,wait,"r")).code());
        verify(identity,never()).refresh("t","u");verifyNoInteractions(packets);
    }
    @Test void identityPortMustReturnTheExactOriginalSession() {
        when(refresh.findAnchor(any(),any())).thenReturn(anchor());
        when(identity.refresh("t","u","old-login")).thenReturn(Optional.of(new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"new-login")));
        assertEquals("ACCESS_REVOKED",assertThrows(MemoryContracts.MemoryException.class,()->service().prepareRefresh(scope,wait,"r")).code());
        verifyNoInteractions(packets);
    }
    @Test void historyKeepsActualRevisionAndRequiresPersistedAuthorization()throws Exception {
        var json=new com.fasterxml.jackson.databind.ObjectMapper();
        var dep=new MemoryContextPacket.Dependency("CURRENT_USER_MESSAGE","source","v",0,0,0);
        var row=new MemoryPacketMapper.PacketRow(b("t"),b("e"),b("packet"),1,b("u"),b("task"),json.writeValueAsString(wait.scope()),"{}",
            json.writeValueAsString(List.of(new MemoryAuthorization.ExecutionGrant("direct","operations","assistant_response"))),
            json.writeValueAsString(Map.of("input_dependencies",List.of(dep))),json.writeValueAsString(List.of(dep)),"d".repeat(64),"e".repeat(64),"f".repeat(64),"c".repeat(64),b("e"),1,0,0,0,1200,900,960);
        when(packets.findPacket(any(),any())).thenReturn(row);
        when(refresh.authorizedRevisions(any(),any())).thenReturn(List.of(2L));
        var opScope=new MemoryRuntimeManifest.Scope(wait.scope(),"task","e","sub","assistant_response","operations");
        var old=new MemoryRuntimeManifest.Operation(opScope,"direct","packet",1,List.of(dep),List.of(dep));
        var newer=new MemoryRuntimeManifest.Operation(opScope,"direct","packet",2,List.of(dep),List.of(dep));
        var manifest=new MemoryRuntimeManifest("runtime","e","packet",2,List.of(old,newer));
        assertEquals(List.of(dep),service().verifyManifest(scope,"e","runtime",manifest));
        when(refresh.authorizedRevisions(any(),any())).thenReturn(List.of());
        assertThrows(MemoryContracts.MemoryException.class,()->service().verifyManifest(scope,"e","runtime",manifest));
        assertEquals(1,old.packetRevision());assertEquals(2,newer.packetRevision());
    }
    @Test void runtimeMustComeFromTheOriginalJavaRunMapping() {
        var authority=mock(MemoryPacketService.class);when(authority.refreshEnabled()).thenReturn(true);when(authority.issuedScope("t","e")).thenReturn(scope);
        var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);when(ai.queryMemoryWait("t","e","w")).thenReturn(wait);
        var service=new MemoryContextResumeService(mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),packets,ai,authority);
        assertEquals("MEMORY_RESUME_CONFLICT",assertThrows(MemoryContracts.MemoryException.class,()->service.onWait("t","e","another-runtime","w","r")).code());
        verify(authority,never()).prepareRefresh(any(),any(),any());verify(ai,never()).resumeMemoryExecution(any(),any(),any());
    }
    @Test void legacyWaitEntryWithoutOriginalRuntimeCannotTransmit() {
        var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);var authority=mock(MemoryPacketService.class);when(authority.refreshEnabled()).thenReturn(true);
        var service=new MemoryContextResumeService(mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),packets,ai,authority);
        assertEquals("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED",assertThrows(MemoryContracts.MemoryException.class,()->service.onWait("t","e","w","r")).code());
        verifyNoInteractions(ai);
    }
    static byte[] b(String s){return s.getBytes(java.nio.charset.StandardCharsets.UTF_8);}
}
