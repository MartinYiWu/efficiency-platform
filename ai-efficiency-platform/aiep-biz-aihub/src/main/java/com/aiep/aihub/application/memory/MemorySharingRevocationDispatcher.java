package com.aiep.aihub.application.memory;

import static com.aiep.aihub.application.memory.MemoryScopeMembershipService.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemorySharingMapper.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 仅撤目标投影的原执行；复用原cleanup端口，不撤原owner私有item或退款。 */
@Service
@ConditionalOnProperty(name="aiep.memory.sharing-enabled",havingValue="true")
public class MemorySharingRevocationDispatcher {
    private final MemorySharingMapper mapper;private final MemoryForgetMapper sources;private final MemoryPacketMapper packets;
    private final AiInvokeFacade ai;private final TransactionTemplate transaction;
    public MemorySharingRevocationDispatcher(MemorySharingMapper mapper,MemoryForgetMapper sources,MemoryPacketMapper packets,AiInvokeFacade ai,PlatformTransactionManager manager){this.mapper=mapper;this.sources=sources;this.packets=packets;this.ai=ai;transaction=new TransactionTemplate(manager);}
    @Scheduled(fixedDelayString="${aiep.memory.sharing-revocation-delay-ms:60000}") public void dispatch() {
        for(var delivery:mapper.due(16)) {
            byte[] token=uuid();if(!Boolean.TRUE.equals(transaction.execute(tx->mapper.claim(delivery,token)==1)))continue;
            boolean complete=false;
            try {complete=cleanup(delivery);}catch(RuntimeException refused){/* 持久次数/截止保留，未知结果不作完成证明。 */}
            boolean finished=complete;transaction.executeWithoutResult(tx->mapper.finishDelivery(delivery,token,finished));
        }
    }
    boolean cleanup(DeliveryPO delivery) {
        var affected=transaction.execute(tx->{
            var source=sources.lockSource(delivery.tenantId(),delivery.projectionId());
            if(source==null||source.deletionEpoch()!=delivery.epoch())throw failure("MEMORY_SOURCE_CHANGED");
            return List.copyOf(sources.listSourceDependencies(delivery.tenantId(),delivery.projectionId()));
        });
        var executions=new TreeMap<String,List<MemoryContextPacket.Dependency>>();
        for(var dep:affected) {
            if(!Set.of("EXECUTION","MESSAGE","SUMMARY","PROPOSAL").contains(dep.targetType()))return false;
            if(dep.rootThreadRef()!=null||dep.childThreadRef()!=null||dep.checkpointNamespace()!=null)return false;
            if(dep.executionId()!=null&&dep.executionId().length>0)executions.computeIfAbsent(text(dep.executionId()),unused->new ArrayList<>())
                    .add(new MemoryContextPacket.Dependency(dep.sourceType(),text(dep.sourceId()),text(dep.sourceVersion()),dep.grantEpoch(),dep.sourceEpoch(),dep.deletionEpoch()));
            else if("EXECUTION".equals(dep.targetType()))return false;
        }
        for(var entry:executions.entrySet()) {
            var packet=packets.findPacket(delivery.tenantId(),b(entry.getKey()));if(packet==null)return false;
            String event="share-cleanup-"+MemoryPacketDigest.canonicalDigest(new com.fasterxml.jackson.databind.ObjectMapper().valueToTree(List.of(text(delivery.eventId()),entry.getKey())));
            var request=new MemoryCleanupRequest(event,packet.executionRevision(),Math.max(packet.grantEpoch()+1,delivery.epoch()),Math.max(packet.sourceEpoch()+1,delivery.epoch()),Math.max(packet.deletionEpoch()+1,delivery.epoch()),MemoryPacketDigest.dependencies(entry.getValue()));
            var receipt=ai.cleanupMemoryExecution(text(delivery.tenantId()),entry.getKey(),request);
            if(receipt==null||!event.equals(receipt.eventId())||!entry.getKey().equals(receipt.executionId())||receipt.deletionEpoch()!=request.deletionEpoch())return false;
            for(String target:List.of("AGENT_STOP","THREADS","SNAPSHOT"))if(receipt.receipts().get(target)==null||!receipt.receipts().get(target).matches("[A-Za-z0-9:_-]{16,160}"))return false;
        }
        return true;
    }
}
