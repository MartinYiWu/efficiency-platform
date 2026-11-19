package com.aiep.aihub.application.memory;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.application.management.*;
import com.aiep.aihub.repository.management.*;
import com.aiep.aihub.repository.management.AiManagementPOs.*;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper.*;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

class MemoryPromotionReviewFixTest {
    final AiManagementMappers repository=mock(AiManagementMappers.class);
    final MemoryEpisodeMapper episodes=mock(MemoryEpisodeMapper.class);
    final IdentityFacade identity=mock(IdentityFacade.class);
    final AiInvokeFacade ai=mock(AiInvokeFacade.class);
    final ObjectMapper json=new ObjectMapper();
    final LocalDateTime now=LocalDateTime.now();
    final AiReleaseService releases=new AiReleaseService(repository,ai,json);
    final MemoryPromotionAssetGuard guard=new MemoryPromotionAssetGuard(episodes,identity);
    static byte[] b(String value){return MemoryMapper.identity(value);}
    AgentVersionPO version(String status,String summary){return new AgentVersionPO("av","agent","1.1.0","customer-service-graph","1",status,summary,"creator",now,null);}
    PromotionPO promotion(String id,String episode,String status){return new PromotionPO(b("tenant"),b(id),b(episode),b("creator"),"WORKFLOW","agent","av","c".repeat(64),status,1,b("request-"+id),"f".repeat(64),"suite","1","a".repeat(64),3,3,b("reviewer"),null);}
    IdentityFacade.Subject actor(String user,String permission){return new IdentityFacade.Subject("tenant",user,Set.of(),permission==null?Set.of():Set.of(permission),Set.of(),Set.of(),List.of(),"login-"+user);}
    void base() {
        ReflectionTestUtils.setField(releases,"promotionGuard",guard);
        when(repository.findAgent("agent")).thenReturn(new AgentDefinitionPO("agent","customer-service","客服","合成","WORKFLOW","ACTIVE","creator",now,"creator",now));
        when(ai.publishCustomerServiceRelease(anyString(),any())).thenAnswer(call->{CustomerServiceReleaseRequest body=call.getArgument(1);return new CustomerServiceReleaseAck("customer-service-release-ack/1",call.getArgument(0),body.snapshotChecksum(),"ACKNOWLEDGED");});
    }
    CustomerServiceReleaseRequest.PromptBinding publishedPrompt(String stage,String suffix,boolean promoted) {
        String definition="pd-"+suffix,version="pv-"+suffix,key="prompt-"+suffix;
        when(repository.findPromptDefinition(definition)).thenReturn(new PromptDefinitionPO(definition,key,"SHARED",null,"名称","合成",stage,"ACTIVE","creator",now,"creator",now));
        var prompt=new PromptVersionPO(version,definition,"1.0.0","PUBLISHED","c".repeat(64),promoted?MemoryPromotionAssetGuard.MARKER+"episode":"普通发布","creator",now,now);
        when(repository.findPromptVersion(version)).thenReturn(prompt);
        when(repository.findPromptVersionsBySnapshot(key,"1.0.0","c".repeat(64))).thenReturn(List.of(prompt));
        var messages=List.of(new PromptMessageTemplatePO("system-"+suffix,version,1,"SYSTEM","system","合成历史规则","TEXT",true,"d".repeat(64)),new PromptMessageTemplatePO("user-"+suffix,version,2,"USER","input","合成任务","TEXT",false,"e".repeat(64)));
        when(repository.listPromptMessages(version)).thenReturn(messages);when(repository.listPromptVariables(version)).thenReturn(List.of());
        return new CustomerServiceReleaseRequest.PromptBinding(stage,1,key,"1.0.0","c".repeat(64),messages.stream().map(message->new CustomerServiceReleaseRequest.PromptMessage(message.ordinal(),message.role(),message.messageKey(),message.contentTemplate(),message.contentFormat(),message.trustedInstruction(),message.checksum(),List.of())).toList());
    }
    CustomerServiceReleaseRequest wire(String checksum,List<CustomerServiceReleaseRequest.PromptBinding> prompts) {
        return new CustomerServiceReleaseRequest("customer-service-release/1","customer-service","1.1.0","customer-service-graph","1","dev",prompts,
                new CustomerServiceReleaseRequest.ModelPolicy("model","1","fake","fake",BigDecimal.ZERO,BigDecimal.ONE,8192,1024,1000,1000,0,"a".repeat(64)),
                new CustomerServiceReleaseRequest.RagPolicy("rag","1",1,10,10,10,5,2048,3,"b".repeat(64)),List.of(new CustomerServiceReleaseRequest.KnowledgeBinding("kb","index",1,true)),List.of(),"customer-service-answer/1","1",checksum);
    }
    @Test void rollbackRechecksExactHistoricalPromptAndNeverReplacesItWithNewBinding() throws Exception {
        base();when(repository.findAgentVersion("av")).thenReturn(version("RELEASED","普通版本"));
        var old=publishedPrompt("intent","old",true);var provisional=wire("0".repeat(64),List.of(old));
        String checksum=ReflectionTestUtils.invokeMethod(releases,"checksum",provisional);var snapshot=wire(checksum,List.of(old));
        when(repository.findRelease("release-old")).thenReturn(new AiReleasePO("release-old","agent","av","dev","RETIRED","snapshot-old","creator",now,null,now));
        when(repository.findReleaseSnapshot("release-old")).thenReturn(new AiReleaseSnapshotPO("snapshot-old","release-old",json.writeValueAsString(snapshot),checksum,"ACKNOWLEDGED",now,now));
        when(repository.listPromptBindings("av")).thenReturn(List.of(new PromptBindingPO("av","intent",1,"pd-new","pv-new",true)));
        when(episodes.findAssetPromotion("PROMPT","pv-old")).thenReturn(promotion("old-promotion","episode","PUBLISHED"));
        when(episodes.assetSourcesCurrent(any(),any())).thenReturn(0);
        assertEquals("MEMORY_PROMOTION_SOURCE_REVOKED",assertThrows(MemoryException.class,()->releases.rollback("release-old")).code());
        verify(ai,never()).publishCustomerServiceRelease(anyString(),any());verify(repository,never()).insertRelease(any(),any());
        when(episodes.assetSourcesCurrent(any(),any())).thenReturn(1);
        var result=releases.rollback("release-old");assertEquals("release-old",result.rolledBackFromReleaseId());
        verify(ai).publishCustomerServiceRelease(anyString(),eq(snapshot));
        verify(repository,never()).listPromptBindings("av");
    }
    @Test void approvedWorkflowStaysValidatedUntilExistingReleaseAcknowledges() {
        base();var state=new AtomicReference<>(version("DRAFT",MemoryPromotionAssetGuard.MARKER+"episode 人工候选"));
        when(repository.findAgentVersion("av")).thenAnswer(call->state.get());doAnswer(call->{state.set(call.getArgument(0));return null;}).when(repository).updateAgentVersion(any());
        var publisher=actor("publisher","memory:promotion:publish");when(identity.refresh("tenant","publisher","login-publisher")).thenReturn(Optional.of(publisher));
        var approval=new AtomicReference<>("REGRESSION_PASSED");when(episodes.findAssetPromotion("AGENT","av")).thenAnswer(call->promotion("promotion","episode",approval.get()));when(episodes.assetSourcesCurrent(any(),any())).thenReturn(1);
        var agents=new AiAgentManagementService(repository);ReflectionTestUtils.setField(agents,"promotionGuard",guard);
        when(repository.findPolicyBinding("av")).thenReturn(new AgentVersionPolicyBindingPO("av","model","rag",null));
        when(repository.findModelPolicy("model")).thenReturn(new ModelPolicyPO("model","agent","model","1","fake","fake",BigDecimal.ZERO,BigDecimal.ONE,8192,1024,1000,1000,0,"PUBLISHED","a".repeat(64),"creator",now,now));
        when(repository.findRagPolicy("rag")).thenReturn(new RagPolicyPO("rag","agent","rag","1",1,10,10,10,5,2048,3,"PUBLISHED","b".repeat(64),"creator",now,now,3,new BigDecimal("0.90"),10,2));
        var bindings=new ArrayList<PromptBindingPO>();for(String stage:List.of("equivalence","conflict_screen","evidence_extract")){publishedPrompt(stage,stage,false);bindings.add(new PromptBindingPO("av",stage,1,"pd-"+stage,"pv-"+stage,true));}
        when(repository.listPromptBindings("av")).thenReturn(bindings);when(repository.listKnowledgeBindings("av")).thenReturn(List.of(new AgentVersionKnowledgeBindingPO("av","kb","index",1,true)));when(repository.isIndexReleaseReady("index")).thenReturn(true);
        var adapter=new MemoryPromotionAssetAdapter(mock(AiPromptManagementService.class),agents,repository);String digest=adapter.digest("WORKFLOW","av");
        adapter.publish(publisher,"WORKFLOW","av",digest);assertEquals("VALIDATED",state.get().status());
        approval.set("PUBLISHED");doAnswer(call->{state.set(version("RELEASED",state.get().changeSummary()));return null;}).when(repository).acknowledgeAndActivateRelease(anyString(),anyString(),eq("agent"),eq("dev"),eq("av"));
        assertEquals("ACTIVE",releases.publish("av","dev").releaseStatus());assertEquals("RELEASED",state.get().status());verify(ai).publishCustomerServiceRelease(anyString(),any());
    }
    EpisodePO episode(String id){return new EpisodePO(b("tenant"),b(id),b("source-owner"),"operations",b("session"),b("execution"),"{}","[]",b("policy"),b("p1"),"SHARED",4,Instant.now().plusSeconds(3600),"key",new byte[1],new byte[12],new byte[16],new byte[32],b("scope"),b("owner-session"),"key",new byte[1],new byte[12],new byte[16],new byte[32],b("approver"),b("request"),"f".repeat(64));}
    @Test void independentReviewQueuesCheckCurrentRolesMembershipAndSources() {
        var serviceEpisodes=mock(MemoryEpisodeService.class);var manager=mock(PlatformTransactionManager.class);when(manager.getTransaction(any())).thenAnswer(call->new SimpleTransactionStatus());ReflectionTestUtils.setField(serviceEpisodes,"transaction",new TransactionTemplate(manager));
        var draft=promotion("draft","allowed","DRAFT");var denied=promotion("denied","denied","DRAFT");var stale=promotion("stale","stale","DRAFT");var ready=promotion("ready","allowed","REGRESSION_PASSED");
        when(episodes.listPromotions(any(),any(),anyBoolean(),anyBoolean())).thenReturn(List.of(draft,denied,stale,ready));
        var allowed=episode("allowed");var forbidden=episode("denied");var expired=episode("stale");when(serviceEpisodes.load("tenant","allowed")).thenReturn(allowed);when(serviceEpisodes.load("tenant","denied")).thenReturn(forbidden);when(serviceEpisodes.load("tenant","stale")).thenReturn(expired);
        when(serviceEpisodes.refresh(allowed)).thenReturn(allowed);when(serviceEpisodes.refresh(forbidden)).thenReturn(forbidden);when(serviceEpisodes.refresh(expired)).thenThrow(new MemoryException("MEMORY_SOURCE_CHANGED"));doThrow(new MemoryException("MEMORY_SCOPE_DENIED")).when(serviceEpisodes).readableShared(any(),eq(forbidden));
        var service=new MemoryPromotionService(serviceEpisodes,episodes,mock(MemoryPromotionAssetAdapter.class));
        var reviewer=actor("reviewer","memory:promotion:regression");when(serviceEpisodes.current(reviewer,null)).thenReturn(reviewer);assertEquals(List.of("draft"),service.list(reviewer).stream().map(item->item.id()).toList());verify(episodes).listPromotions(eq(b("tenant")),eq(b("reviewer")),eq(true),eq(false));
        var publisher=actor("publisher","memory:promotion:publish");when(serviceEpisodes.current(publisher,null)).thenReturn(publisher);assertEquals(List.of("ready"),service.list(publisher).stream().map(item->item.id()).toList());verify(episodes).listPromotions(eq(b("tenant")),eq(b("publisher")),eq(false),eq(true));
        var ordinary=actor("member",null);when(serviceEpisodes.current(ordinary,null)).thenReturn(ordinary);assertTrue(service.list(ordinary).isEmpty());
    }
}
