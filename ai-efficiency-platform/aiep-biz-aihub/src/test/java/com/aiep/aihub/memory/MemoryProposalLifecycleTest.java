package com.aiep.aihub.memory;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.api.memory.MemoryProposalContracts.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.repository.memory.MemoryProposalMapper.ProposalPO;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;

class MemoryProposalLifecycleTest {
    final MemoryProposalMapper mapper=mock(MemoryProposalMapper.class);
    final MemoryMapper memories=mock(MemoryMapper.class);
    final MemoryPacketMapper packets=mock(MemoryPacketMapper.class);
    final MemorySummaryMapper summary=mock(MemorySummaryMapper.class);
    final MemoryDependencyService dependencies=mock(MemoryDependencyService.class);
    final MemoryScopePolicy scopes=mock(MemoryScopePolicy.class);
    final MemorySessionBindingService bindings=mock(MemorySessionBindingService.class);
    final MemoryPolicyService policies=mock(MemoryPolicyService.class);
    final MemoryPreferenceService preferences=mock(MemoryPreferenceService.class);
    final PlatformTransactionManager manager=mock(PlatformTransactionManager.class);
    final MemoryValueCodec codec=MemoryPreferenceTest.codec();
    final IdentityFacade.Subject actor=new IdentityFacade.Subject("tenant","user",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"new-login-next-day");
    final MemoryScopeDTO scope=new MemoryScopeDTO("tenant","user","operations","operations","CONVERSATION","session");
    final ObjectMapper json=new ObjectMapper();
    final MemorySummarySourceService sources=new MemorySummarySourceService(false,summary,memories,packets,dependencies,codec,scopes,bindings,mock(IdentityFacade.class),manager,Clock.systemUTC());
    MemoryProposalService service(boolean enabled){return new MemoryProposalService(enabled,mapper,memories,packets,sources,scopes,bindings,policies,preferences,new MemoryConflictService(),dependencies,codec,manager);}
    static byte[] b(String value){return MemoryMapper.identity(value);}
    ProposalPO row(String status,long revision,boolean scrubbed) throws Exception {
        var sealed=codec.seal(b("tenant"),b("proposal:item"),b("proposal"),"zh-CN");
        return new ProposalPO(b("tenant"),b("proposal"),b("item"),b("original-task"),b("expired-execution"),b("user"),"operations","operations",b("session"),"response.language","CONFLICT_CANDIDATE",status,revision,2,b("policy"),b("policy/1"),Instant.now().plusSeconds(86400),"[\"message\"]",json.writeValueAsString(List.of(new Dependency("MESSAGE","message","bodyhash",0,1,0))),sealed.keyVersion(),scrubbed?null:sealed.payload(),scrubbed?null:sealed.nonce(),scrubbed?null:sealed.tag(),scrubbed?null:sealed.hmac(),"ACCEPTED".equals(status)?b("decision-request"):null,"ACCEPTED".equals(status)?b("user"):null,"ACCEPTED".equals(status)?"CONFIRM":null,0,2,"ACCEPTED".equals(status)?b("new-version"):null);
    }
    void setup(ProposalPO row) {
        when(manager.getTransaction(any())).thenAnswer(call->new SimpleTransactionStatus());
        when(mapper.readProposal(any(),any())).thenReturn(row);
        when(mapper.lockProposal(any(),any())).thenReturn(row);
        when(memories.findItemForUpdate(any(),any())).thenReturn(new MemoryItemPO(b("tenant"),b("item"),"USER",b("user"),b("user"),"operations","operations","USER_PRIVATE",MemoryMapper.privateScope("user","operations"),"assistant_response","response.language","LIVE",2,b("old-version"),0,0,0));
        String config="{\"artifacts\":{\"schema_version\":\"memory-artifacts/1\",\"index_mode\":\"NOT_PROVISIONED\",\"index_backends\":[]},\"proposals\":{\"enabled\":true,\"retentionSeconds\":86400,\"sourceTypes\":[\"MESSAGE\"]}}";
        when(summary.lockPublishedPolicy(any(),any())).thenReturn(new PolicyPO(b("policy"),b("policy/1"),config,new byte[32],"memory-policy/1"));
        when(summary.lockMessage(any(),any(),any(),any(),any())).thenReturn(new MemorySummaryMapper.MessagePO(b("message"),b("original-run"),"合成原文","bodyhash","user",true));
        when(dependencies.requireCurrent(any(),any())).thenReturn(Instant.now().plusSeconds(86400));
        when(policies.require(any(),any(),any())).thenReturn(new MemoryPolicyService.Published(b("policy"),b("policy/1"),86400));
        when(mapper.resolve(any(),any(),any(),any(),any(),anyLong(),any())).thenReturn(1);
        when(mapper.invalidate(any(),any())).thenReturn(1);
        when(packets.insertDependency(any(),any(),any(),any(),any(),any(),anyLong(),anyLong(),anyLong())).thenReturn(1);
    }
    @Test void finiteInputAndConflictsNeverSelectLatestValue() {
        var conflicts=new MemoryConflictService();
        assertEquals(Action.CONFLICT_CANDIDATE,conflicts.classify(b("new"),b("old"),List.of()));
        assertEquals(Action.CONFLICT_CANDIDATE,conflicts.classify(b("same"),b("same"),List.of(b("different"))));
        assertEquals(Action.NOOP,conflicts.classify(b("same"),b("same"),List.of()));
        assertEquals(Action.ADD,conflicts.classify(b("new"),null,List.of()));
        assertThrows(MemoryException.class,()->new Submission(scope,"execution",List.of("message"),Collections.nCopies(17,new Candidate("PREFERENCE","response.language","zh-CN")),"request"));
        assertEquals(1,new Submission(scope,"execution",List.of("message"),Collections.nCopies(2,new Candidate("PREFERENCE","response.language","zh-CN")),"request").candidates().size());
        assertThrows(MemoryException.class,()->new Candidate("PREFERENCE","response.language","😀".repeat(100)));
        assertThrows(MemoryException.class,()->service(false).get(actor,scope,"proposal"));
        verifyNoInteractions(mapper,packets,preferences);
    }
    @Test void nextDayConfirmationReusesAuthorityWithoutOriginalRunOrIndex() throws Exception {
        var pending=row("PENDING",0,false);setup(pending);var accepted=row("ACCEPTED",1,false);
        when(mapper.lockProposal(any(),any())).thenReturn(pending,accepted);
        when(preferences.correct(any(),eq("item"),any())).thenReturn(new Preference("item","new-version",scope,"response.language","zh-CN",3));
        var result=service(true).decide(actor,"proposal",new DecisionCommand(scope,0,2,Decision.CONFIRM,"decision-request"));
        assertEquals(Status.ACCEPTED,result.status());assertEquals("NOT_REQUESTED",result.indexStatus());assertEquals("new-version",result.versionId());
        verify(preferences).correct(eq(actor),eq("item"),argThat(command->command.expectedRevision()==2&&"zh-CN".equals(command.value())));
        verify(summary,never()).findAnchor(any(),any());verify(packets,never()).findPacket(any(),any());
        verify(packets).insertDependency(any(),any(),eq("MEMORY_VERSION"),any(),any(),isNull(),eq(0L),eq(1L),eq(0L));
    }
    @Test void suppressionAndRevisionPreventConfirmation() throws Exception {
        var pending=row("PENDING",0,false);setup(pending);
        assertThrows(MemoryException.class,()->service(true).decide(actor,"proposal",new DecisionCommand(scope,1,2,Decision.CONFIRM,"decision-request")));
        verifyNoInteractions(preferences);
        when(memories.countPreferenceSuppression(any(),any(),any(),any(),any())).thenReturn(1);
        var suppressed=row("SUPPRESSED",1,true);when(mapper.lockProposal(any(),any())).thenReturn(suppressed);
        var result=service(true).decide(actor,"proposal",new DecisionCommand(scope,0,2,Decision.CONFIRM,"other-request"));
        assertEquals(Status.SUPPRESSED,result.status());assertNull(result.value());verifyNoInteractions(preferences);
    }
}
