package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContextUsage;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.operation.OperationRunMapper;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemoryRuntimeManifest;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class MemoryContextUsageService {
    private final MemoryScopePolicy scopes;
    private final MemorySessionBindingService bindings;
    private final MemoryPacketService packets;
    private final OperationRunMapper operationRuns;
    private final CustomerServiceMappers customerRuns;
    private final AiInvokeFacade ai;
    private final ObjectProvider<MemorySummaryService> summaries;

    public MemoryContextUsageService(MemoryScopePolicy scopes,MemorySessionBindingService bindings,
            MemoryPacketService packets,OperationRunMapper operationRuns,CustomerServiceMappers customerRuns,
            AiInvokeFacade ai,ObjectProvider<MemorySummaryService> summaries) {
        this.scopes=scopes;this.bindings=bindings;this.packets=packets;this.operationRuns=operationRuns;
        this.customerRuns=customerRuns;this.ai=ai;this.summaries=summaries;
    }

    public MemoryContextUsage read(String topAgent,String sessionId,String runId) {
        var actor=scopes.currentActor();
        var scope=new MemoryScopeDTO(actor.tenantId(),actor.userId(),topAgent,topAgent,"CONVERSATION",sessionId);
        scopes.require(actor,scope,Set.of());bindings.require(actor,scope);
        var service=summaries.getIfAvailable();
        var segments=service==null?List.<MemoryContextUsage.SegmentView>of():service.listCommitted(actor,scope).stream()
            .map(item->new MemoryContextUsage.SegmentView(item.segmentId(),item.firstSequence(),item.lastSequence(),
                item.expiresAt(),item.sourceCount(),item.freeTextQuality())).toList();
        if(runId==null||runId.isBlank())return new MemoryContextUsage(topAgent,sessionId,null,
            segments.isEmpty()?"EMPTY":"AVAILABLE",List.of(),segments);
        MemoryMapper.identity(runId);
        String runtime;
        if("operations".equals(topAgent)) {
            var run=operationRuns.selectById(runId);
            if(run==null||!actor.tenantId().equals(run.getTenantId())||!sessionId.equals(run.getConversationId()))throw new MemoryException("MEMORY_SCOPE_DENIED");
            runtime=run.getAgentRunId();
        } else if("customer-service".equals(topAgent)) {
            var run=customerRuns.findRun(runId,actor.tenantId());
            if(run==null||!sessionId.equals(run.conversationId()))throw new MemoryException("MEMORY_SCOPE_DENIED");
            runtime=run.agentRunId();
        } else throw new MemoryException("MEMORY_SCOPE_DENIED");
        if(!packets.enabled()||runtime==null)return new MemoryContextUsage(topAgent,sessionId,runId,"EMPTY",List.of(),segments);
        if(!packets.issuedScope(actor.tenantId(),runId).equals(scope))throw new MemoryException("MEMORY_SCOPE_DENIED");
        var manifest=ai.queryMemoryManifest(actor.tenantId(),runId);
        packets.verifyManifest(scope,runId,runtime,manifest);
        return new MemoryContextUsage(topAgent,sessionId,runId,"AVAILABLE",manifest.manifests().stream().map(this::node).toList(),segments);
    }

    public MemoryContextUsage.SegmentDetail summary(String topAgent,String sessionId,String id) {
        var actor=scopes.currentActor();
        var scope=new MemoryScopeDTO(actor.tenantId(),actor.userId(),topAgent,topAgent,"CONVERSATION",sessionId);
        scopes.require(actor,scope,Set.of());bindings.require(actor,scope);
        var service=summaries.getIfAvailable();
        if(service==null)throw new MemoryException("MEMORY_NOT_FOUND");
        var segment=service.readCommitted(actor,scope,id);
        return new MemoryContextUsage.SegmentDetail(segment.segmentId(),"UNVERIFIED",entry(segment.goal()),
            segment.confirmedConstraints().stream().map(this::entry).toList(),segment.decisions().stream().map(this::entry).toList(),
            segment.rejectedOptions().stream().map(this::entry).toList(),segment.openQuestions().stream().map(this::entry).toList(),
            segment.importantRefs().stream().map(this::entry).toList(),segment.uncertainties().stream().map(this::entry).toList());
    }
    private MemoryContextUsage.EntryView entry(com.aiep.aihub.api.memory.MemorySummaryContracts.Entry item) {
        return new MemoryContextUsage.EntryView(item.text(),item.contentOrigin().name(),item.decisionStatus().name(),
            item instanceof com.aiep.aihub.api.memory.MemorySummaryContracts.RejectedOption rejected?rejected.reason():null);
    }
    private MemoryContextUsage.NodeUsage node(MemoryRuntimeManifest.Operation operation) {
        var decision=operation.decision();var measurement=operation.measurement();
        var reasons=operation.exclusions()==null?Map.<String,Long>of():operation.exclusions().stream()
            .filter(pair->pair.size()==2).map(pair->pair.get(1)).collect(Collectors.groupingBy(reason->reason,LinkedHashMap::new,Collectors.counting()));
        return new MemoryContextUsage.NodeUsage(operation.nodeId(),measurement==null||!Boolean.TRUE.equals(measurement.verified())?null:measurement.totalUpperBound(),
            decision==null?null:decision.inputLimit(),decision==null?null:decision.freeTokens(),operation.cpuBeforeTokens(),operation.cpuAfterTokens(),
            operation.summaryBeforeTokens(),operation.summaryAfterTokens(),operation.outputReserveTokens(),decision==null?"UNKNOWN":decision.status(),
            operation.summaryCasStatus()==null?"not-applied":operation.summaryCasStatus(),
            operation.summaryAdoptionStatus()==null?"not-applied":operation.summaryAdoptionStatus(),"NOT_REPORTED",null,
            reasons.entrySet().stream().map(item->new MemoryContextUsage.Omission(item.getKey(),item.getValue())).toList());
    }
}
