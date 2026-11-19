package com.aiep.aihub.memory;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemorySharingContracts.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.repository.memory.MemorySharingMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;

class MemorySharingPolicyTest {
    final MemorySharingMapper mapper=mock(MemorySharingMapper.class);final MemoryMapper memories=mock(MemoryMapper.class);
    final MemoryPacketMapper packets=mock(MemoryPacketMapper.class);final MemoryDependencyService dependencies=mock(MemoryDependencyService.class);
    final MemoryPolicyService policies=mock(MemoryPolicyService.class);final IdentityFacade identity=mock(IdentityFacade.class);
    final PlatformTransactionManager manager=mock(PlatformTransactionManager.class);
    final IdentityFacade.Subject actor=new IdentityFacade.Subject("tenant","member",Set.of("department"),Set.of(),Set.of(),Set.of(),List.of(),"login");
    static byte[] b(String value){return MemoryMapper.identity(value);}
    MemorySharingService sharing(boolean enabled) {
        when(manager.getTransaction(any())).thenAnswer(call->new SimpleTransactionStatus());
        when(identity.refresh("tenant","member","login")).thenReturn(Optional.of(actor));
        return new MemorySharingService(new MemoryScopeMembershipService(enabled,mapper,identity,manager),mapper,memories,packets,dependencies,policies,MemoryPreferenceTest.codec());
    }
    @Test void disabledDoesNotReadNewTables() {
        assertThrows(MemoryException.class,()->sharing(false).listAgentGrants(actor,"operations"));verifyNoInteractions(mapper,memories,packets);
    }
    @Test void crossAgentGrantRejectsChatDerivedPreferenceAndKeepsPrivateValue() {
        var service=sharing(true);var expiry=Instant.now().plusSeconds(3600);
        when(memories.findItemForUpdate(any(),any())).thenReturn(new MemoryItemPO(b("tenant"),b("item"),"USER",b("member"),b("member"),"operations","operations","USER_PRIVATE",MemoryMapper.privateScope("member","operations"),"assistant_response","response.language","LIVE",2,b("version"),0,0,0));
        when(memories.findPreferenceVersion(any(),any(),any())).thenReturn(new VersionRow(b("tenant"),b("item"),b("version"),"ACTIVE",new byte[1],"key",new byte[12],new byte[16],new byte[32],b("policy"),b("policy/1"),b("decision"),null,expiry,2));
        when(dependencies.dependencies(any(),eq("MEMORY_VERSION"),eq("item"),eq("version"))).thenReturn(List.of(new Dependency("MESSAGE","private-chat","hash",0,1,0)));
        var error=assertThrows(MemoryException.class,()->service.grantAgent(actor,new GrantCommand("operations","item","version","customer-service",2,expiry.minusSeconds(1),"request")));
        assertEquals("MEMORY_SHARING_SOURCE_DENIED",error.code());verify(mapper,never()).insertGrant(any());verify(memories,never()).compareAndSetCurrent(any(),any(),anyLong(),any(),any());
    }
    @Test void leavingScopeRevokesOnlyReadersProjectionAndEnqueuesCleanup() {
        var service=sharing(true);var expiry=Instant.now().plusSeconds(3600);
        var scope=new ScopePO(b("tenant"),b("scope"),"PROJECT",null,b("owner"),b("approver"),"ACTIVE",4,expiry,b("create"),"a".repeat(64));
        var member=new MemberPO(b("tenant"),b("scope"),b("member"),"ACTIVE",2,b("accept"));
        var projection=new ProjectionPO(b("tenant"),b("projection"),b("grant"),b("member"),"operations",1,2,"ACTIVE",expiry,null);
        when(mapper.lockScope(any(),any())).thenReturn(scope);when(mapper.lockMember(any(),any(),any())).thenReturn(member);
        when(mapper.listMemberProjections(any(),any(),any())).thenReturn(List.of(projection));when(mapper.updateMember(any(),eq("LEFT"),any())).thenReturn(1);
        when(mapper.advanceScope(any())).thenReturn(1);when(mapper.revokeProjection(any())).thenReturn(1);when(mapper.revokeProjectionSource(any())).thenReturn(1);
        when(packets.findSource(any(),any())).thenReturn(new MemoryPacketMapper.SourceState("MEMORY_SHARE_GRANT",b("projection"),b("1"),1,2,1,expiry,true));
        when(memories.insertOutbox(any(),any(),any(),any(),eq("MEMORY_SHARE_REVOKED"),eq(1L))).thenReturn(1);
        service.membership(actor,"scope",new MembershipCommand(2,"LEAVE","leave-request"));
        verify(mapper).revokeProjection(eq(projection));verify(mapper).listMemberProjections(any(),any(),eq(b("member")));
        verify(memories,never()).compareAndSetCurrent(any(),any(),anyLong(),any(),any());verify(mapper,never()).updateGrant(any(),any());
        verify(memories).advanceTombstone(any(),eq("SOURCE"),eq(b("projection")),eq(1L),eq(1L),eq(2L));
    }
}
