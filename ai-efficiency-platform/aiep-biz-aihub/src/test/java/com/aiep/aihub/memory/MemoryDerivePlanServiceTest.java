package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryContracts;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.application.operation.*;
import com.aiep.aihub.web.operation.OperationAssistantController;
import com.aiep.aihub.web.memory.MemoryActorResolver;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import static com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/** 三条编排边界；真实持久fp/原活帧/费用与主链由root一次合批实际验证。 */
class MemoryDerivePlanServiceTest {
    @Test void httpJsonRoundTripKeepsFrozenBindingAndResponseButRejectsChangedEpoch()throws Exception {
        var wire=new ObjectMapper().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        var scope=new Scope("t","u","operations","operations","CONVERSATION","session");
        var businessScope=new MemoryScopeDTO("t","u","operations","operations","CONVERSATION","session");
        var source=new Dependency("MESSAGE","message","v1",0,1,0);
        var decision=new Dependency("USER_PREFERENCE_DECISION","decision","v1",0,1,0);
        long expires=java.time.Instant.now().getEpochSecond()+900;
        var critical=new CriticalValue("language",CriticalKind.CONSTRAINT,"zh-CN",null);
        var entry=new SummaryEntry("claim","language",ContentOrigin.USER_REQUIREMENT,DecisionStatus.CONFIRMED,List.of(source),decision,List.of(critical));
        var event=new SummaryBasisEvent(decision,"claim",Authority.USER,entry.contentOrigin(),entry.decisionStatus(),entry.criticalValues(),null);
        var metadata=new SummaryInputSource(source,scope,1,"group",List.of(source),List.of(source,decision),true,SourceKind.ORIGINAL,Set.of(SourcePurpose.SUMMARY),"summary-scope",null,"summary-retention",null,expires,entry.criticalValues());
        var frozen=new MemorySummarySourceService.FrozenSources(scope,List.of(metadata),List.of(event),List.of(entry),1,1,0,expires);
        var plan=new MemorySummarySourceService.FrozenPlan("plan","execution","task",expires,frozen,List.of("Original"));
        var request=new MemoryDeriveRequest("memory-derive/1","plan","0".repeat(64),"runtime","OPERATIONS","runtime","plan","execution","budget",expires,
            new MemoryRuntimeManifest.Scope(scope,"task","execution","direct","assistant_response","operations"),"SUMMARY","baseline",new MemoryDeriveRequest.Assets("memory","window","model","prompt","schema"),
            List.of(new MemoryDeriveRequest.FrozenSource(wire.valueToTree(metadata),"Original",MemoryDeriveRequest.sha256("Original"))),wire.valueToTree(frozen.events()),wire.valueToTree(frozen.requiredEntries()),1L,1L,"plan");
        request=wire.readValue(wire.writeValueAsBytes(request),MemoryDeriveRequest.class);
        assertFalse(request.events().equals(wire.valueToTree(frozen.events())));
        var service=new MemoryDerivePlanService(true,null,null,null,(com.aiep.aihub.repository.operation.OperationRunMapper)null);
        var verify=MemoryDerivePlanService.class.getDeclaredMethod("verifyFrozen",MemoryDeriveRequest.class,MemoryScopeDTO.class,String.class,String.class,MemorySummarySourceService.FrozenPlan.class);verify.setAccessible(true);
        verify.invoke(service,request,businessScope,"execution","plan",plan);
        var watermark=new SummaryWatermark(1,1,1);
        var segment=new SummarySegment("segment",scope,List.of(source),watermark,entry,List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),metadata.sourceDependencies(),expires);
        var criticalDigest=MemoryDerivePlanService.class.getDeclaredMethod("criticalDigest",MemoryDeriveRequest.class,SummarySegment.class);criticalDigest.setAccessible(true);
        var candidate=wire.createObjectNode();candidate.put("mode","SUMMARY");candidate.set("summary",wire.valueToTree(segment));candidate.putArray("proposals");
        var validation=wire.createObjectNode();validation.put("free_text_quality","UNVERIFIED");validation.put("commit_status","NOT_COMMITTED");validation.put("session_revision",1);validation.put("source_revision",1);validation.set("source_watermark",wire.valueToTree(watermark));validation.put("frozen_critical_digest",(String)criticalDigest.invoke(null,request,segment));validation.set("source_dependencies",wire.valueToTree(metadata.sourceDependencies()));validation.put("expires_at",expires);
        var benefit=wire.valueToTree(Map.of("status","BENEFICIAL","reason","SUMMARY_BENEFIT_VERIFIED","T_before",200,"T_after",100,"commit_status","NOT_COMMITTED"));
        var response=new MemoryDeriveResponse("memory-derive-result/1","memory.derive",request.planId(),request.planFingerprint(),request.runtimeId(),request.runId(),request.operationId(),request.executionScope(),request.assets(),request.baselineRef(),candidate,validation,benefit);
        response=wire.readValue(wire.writeValueAsBytes(response),MemoryDeriveResponse.class);
        var verifyResponse=MemoryDerivePlanService.class.getDeclaredMethod("verifyResponse",MemoryDeriveRequest.class,MemoryDeriveResponse.class,MemorySummarySourceService.FrozenPlan.class);verifyResponse.setAccessible(true);
        assertEquals(segment,verifyResponse.invoke(null,request,response,plan));
        var changed=(ObjectNode)wire.valueToTree(request);((ObjectNode)changed.path("events").get(0).path("event_ref")).put("source_epoch",2);
        var changedRequest=wire.treeToValue(changed,MemoryDeriveRequest.class);
        var rejected=assertThrows(java.lang.reflect.InvocationTargetException.class,()->verify.invoke(service,changedRequest,businessScope,"execution","plan",plan));
        assertEquals("DERIVE_BINDING_CONFLICT",((MemoryContracts.MemoryException)rejected.getCause()).code());
        var integer=wire.readTree("{\"epoch\":0}");
        assertEquals(MemoryPacketDigest.canonicalDigest(integer),MemoryPacketDigest.canonicalDigest(wire.createObjectNode().put("epoch",0L)));
        assertNotEquals(MemoryPacketDigest.canonicalDigest(integer),MemoryPacketDigest.canonicalDigest(wire.readTree("{\"epoch\":0.0}")));
        assertNotEquals(MemoryPacketDigest.canonicalDigest(integer),MemoryPacketDigest.canonicalDigest(wire.readTree("{\"epoch\":\"0\"}")));
    }
    @Test void defaultOffCannotCreateAPlanOrCallAgent() {
        var sources=mock(MemorySummarySourceService.class);var summaries=mock(MemorySummaryService.class);var ai=mock(AiInvokeFacade.class);
        var service=new MemoryDerivePlanService(false,sources,summaries,ai,(com.aiep.aihub.repository.operation.OperationRunMapper)null);
        assertEquals("MEMORY_DERIVE_FEATURE_DISABLED",assertThrows(MemoryContracts.MemoryException.class,()->service.generateAndCommit(null,null,"execution","plan",null,null)).code());
        verifyNoInteractions(sources,summaries,ai);
    }
    @Test void missingOriginalFrameRequestNeverBuildsANewControlOrBudget() {
        var sources=mock(MemorySummarySourceService.class);when(sources.enabled()).thenReturn(true);var ai=mock(AiInvokeFacade.class);
        var service=new MemoryDerivePlanService(true,sources,mock(MemorySummaryService.class),ai,(com.aiep.aihub.repository.operation.OperationRunMapper)null);
        assertEquals("DERIVE_ORIGINAL_FRAME_REQUIRED",assertThrows(MemoryContracts.MemoryException.class,()->service.generateAndCommit(null,null,"execution","plan",null,null)).code());
        verifyNoInteractions(ai);
    }
    @Test void internalDeriveEventProjectsBeforeCpuHandlerAndNeverReachesEmployeeSse()throws Exception {
        var service=mock(OperationAssistantService.class);var controller=new OperationAssistantController(service,mock(MemoryActorResolver.class));
        var emitter=mock(SseEmitter.class);var actor=new OperationActor("t","u","original-login");
        var event=new OperationAgentRunEvent("operation-run-event/1","memory_derive_required","runtime",3,Map.of("plan_id","plan","baseline_ref","baseline"));
        var send=OperationAssistantController.class.getDeclaredMethod("sendEvent",SseEmitter.class,String.class,OperationAgentRunEvent.class,OperationActor.class);send.setAccessible(true);
        send.invoke(controller,emitter,"execution",event,actor);
        var order=inOrder(service);order.verify(service).projectEvent("execution",event,actor);order.verify(service).onMemoryDerive("execution",event,actor);
        verifyNoInteractions(emitter);
    }
}
