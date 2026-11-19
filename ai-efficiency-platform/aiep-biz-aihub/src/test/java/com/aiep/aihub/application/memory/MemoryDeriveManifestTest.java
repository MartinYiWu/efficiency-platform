package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.operation.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Clock;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import static com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryDeriveManifestTest {
    @Test void derivedManifestReconstructsBoundRequestAndUsesOnlyFrozenSources()throws Exception {
        var wire=new ObjectMapper().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        var scope=new MemoryScopeDTO("t","u","operations","operations","CONVERSATION","session");
        var neutral=new MemoryContextEnvelope.Scope("t","u","operations","operations","CONVERSATION","session");
        var source=new MemoryContextPacket.Dependency("MESSAGE","old","v1",0,1,0);
        var current=new MemoryContextPacket.Dependency("CURRENT_USER_MESSAGE","current","v1",0,1,0);
        long expiry=java.time.Instant.now().getEpochSecond()+900;
        var metadata=new SummaryInputSource(source,neutral,1,"group",List.of(source),List.of(source),true,SourceKind.ORIGINAL,Set.of(SourcePurpose.SUMMARY),"key",null,"memory",null,expiry,List.of());
        var entry=new SummaryEntry("claim","synthetic",ContentOrigin.UNCONFIRMED_INFERENCE,DecisionStatus.UNRESOLVED,List.of(source),null,List.of());
        var frozen=new MemorySummarySourceService.FrozenSources(neutral,List.of(metadata),List.of(),List.of(entry),1,1,0,expiry);
        var opScope=new MemoryRuntimeManifest.Scope(neutral,"task","execution","direct","assistant_response","operations");
        var request=new MemoryDeriveRequest("memory-derive/1","plan","0".repeat(64),"runtime","OPERATIONS","runtime","plan","parent","budget",expiry,opScope,"SUMMARY","baseline",
            new MemoryDeriveRequest.Assets("memory","window","model","derive-prompt/2","derive-schema/2"),
            List.of(new MemoryDeriveRequest.FrozenSource(wire.valueToTree(metadata),"Original",MemoryDeriveRequest.sha256("Original"))),wire.valueToTree(List.of()),wire.valueToTree(List.of(entry)),1L,1L,"plan");
        var full=(ObjectNode)wire.valueToTree(request);full.put("plan_fingerprint",request.canonicalFingerprint());request=wire.treeToValue(full,MemoryDeriveRequest.class);
        var header=full.deepCopy();header.remove(List.of("sources","events","required_entries"));header.put("logical_stage_id","plan");header.put("physical_operation_id","physical-slot");
        var packet=mock(MemoryPacketMapper.PacketRow.class);when(packet.scopeJson()).thenReturn(wire.writeValueAsString(neutral));
        when(packet.tenantId()).thenReturn("t".getBytes());when(packet.userId()).thenReturn("u".getBytes());when(packet.taskId()).thenReturn("task".getBytes());when(packet.packetId()).thenReturn("packet".getBytes());when(packet.parentAuthorizationRef()).thenReturn("parent".getBytes());when(packet.packetRevision()).thenReturn(1L);
        when(packet.referencesJson()).thenReturn(wire.writeValueAsString(Map.of("derive_plan_id","plan","input_dependencies",List.of(current))));
        when(packet.dependenciesJson()).thenReturn(wire.writeValueAsString(List.of(current,source)));
        when(packet.grantsJson()).thenReturn(wire.writeValueAsString(List.of(new MemoryAuthorization.ExecutionGrant("direct","operations","assistant_response"))));
        var policy=new MemoryAuthorization.Policy("policy","memory","operations",List.of("operations"),true,List.of(),List.of(),List.of(),List.of(),List.of(),true,false,true,List.of("MESSAGE","CURRENT_USER_MESSAGE"),0,0,0,1,"disabled","block","1","none","none");
        when(packet.policyJson()).thenReturn(wire.writeValueAsString(policy));
        var mapper=mock(MemorySummaryMapper.class);var packets=mock(MemoryPacketMapper.class);var dependencies=mock(MemoryDependencyService.class);
        when(packets.findPacket(any(),any())).thenReturn(packet);
        var sources=spy(new MemorySummarySourceService(true,mapper,mock(MemoryMapper.class),packets,dependencies,mock(MemoryValueCodec.class),mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),mock(com.aiep.identity.api.IdentityFacade.class),mock(PlatformTransactionManager.class),Clock.systemUTC()));
        var plan=mock(MemorySummaryMapper.PlanPO.class);when(plan.state()).thenReturn("COMMITTED");when(plan.transportFingerprint()).thenReturn(request.planFingerprint());when(plan.executionId()).thenReturn("execution".getBytes());when(plan.taskId()).thenReturn("task".getBytes());when(plan.policyVersionId()).thenReturn("memory".getBytes());when(plan.originalDeadline()).thenReturn(expiry);
        when(mapper.findPlan(any(),eq("key"),any())).thenReturn(plan);doReturn("key").when(sources).scopeKey(scope);doReturn(frozen).when(sources).openPlan(plan);doReturn(new MemorySummarySourceService.Revalidated(frozen,List.of("Original"))).when(sources).revalidate(scope,"key",plan,frozen);
        var runs=mock(OperationRunMapper.class);var run=new OperationRunPO();run.setTenantId("t");run.setConversationId("session");run.setAgentRunId("runtime");run.setStatus("running");when(runs.selectForUpdate("execution","t")).thenReturn(run);
        var derive=new MemoryDerivePlanService(true,sources,null,null,runs);
        var service=new MemoryPacketService(true,mock(MemoryMapper.class),packets,mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),mock(MemoryPolicyService.class),mock(MemoryPreferenceService.class),dependencies,mock(MemoryValueCodec.class),mock(PlatformTransactionManager.class),Clock.systemUTC());
        var field=MemoryPacketService.class.getDeclaredField("derivePlans");field.setAccessible(true);field.set(service,derive);
        var op=wire.createObjectNode();op.set("scope",wire.valueToTree(opScope));op.put("node_id","memory.derive");op.put("packet_id","packet");op.put("packet_revision",1);op.set("safety_dependencies",wire.valueToTree(List.of(source)));op.set("selected_sources",wire.valueToTree(List.of(source)));op.put("operation_id","physical-slot");op.put("model_version","model");op.put("prompt_version","derive-prompt/2");op.put("output_schema_version","derive-schema/2");op.put("policy_version","derive/1");op.put("derive_binding_json",wire.writeValueAsString(header));
        var actual=wire.readValue(wire.writeValueAsBytes(op),MemoryRuntimeManifest.Operation.class);
        assertEquals(List.of(source),service.verifyManifest(scope,"execution","runtime",new MemoryRuntimeManifest("runtime","execution","packet",1,List.of(actual))));
        for(String mutation:List.of("assets","runtime","source","binding","physical")) {
            var bad=op.deepCopy();
            if(mutation.equals("assets")){var changed=header.deepCopy();((ObjectNode)changed.path("assets")).put("model_ref","forged");bad.put("model_version","forged");bad.put("derive_binding_json",wire.writeValueAsString(changed));}
            else if(mutation.equals("runtime")){var changed=header.deepCopy();changed.put("runtime_id","other");bad.put("derive_binding_json",wire.writeValueAsString(changed));}
            else if(mutation.equals("source")){bad.set("safety_dependencies",wire.valueToTree(List.of(current)));bad.set("selected_sources",wire.valueToTree(List.of(current)));}
            else if(mutation.equals("physical"))bad.put("operation_id","other-slot");
            else bad.remove("derive_binding_json");
            var forged=wire.treeToValue(bad,MemoryRuntimeManifest.Operation.class);
            assertThrows(RuntimeException.class,()->service.verifyManifest(scope,"execution","runtime",new MemoryRuntimeManifest("runtime","execution","packet",1,List.of(forged))));
        }
        assertFalse(actual.safetyDependencies().contains(current));
        doThrow(new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_KEY_UNAVAILABLE")).when(sources).openPlan(plan);
        var unavailable=assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,
            ()->service.verifyManifest(scope,"execution","runtime",new MemoryRuntimeManifest("runtime","execution","packet",1,List.of(actual))));
        assertEquals("MEMORY_KEY_UNAVAILABLE",unavailable.code());
    }
}
