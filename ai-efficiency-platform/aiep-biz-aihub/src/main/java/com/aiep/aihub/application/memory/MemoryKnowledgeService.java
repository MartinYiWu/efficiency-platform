package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.knowledge.api.KnowledgeFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.databind.*;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemoryCleanupRequest;

/** Java当前知识Facade签目录；只读metadata，不把Agent检索结果当权限或读跨模块仓储。 */
@Service
public class MemoryKnowledgeService {
    private static final ObjectMapper JSON=new ObjectMapper();
    private final boolean enabled;private final KnowledgeFacade knowledge;private final AiManagementMappers management;
    private final MemoryKnowledgeMapper mapper;private final MemoryPacketMapper packets;private final MemoryMapper memories;
    private final MemoryForgetMapper sources;private final AiInvokeFacade ai;private final TransactionTemplate transaction;
    public MemoryKnowledgeService(@Value("${aiep.memory.knowledge-lineage-enabled:false}") boolean enabled,KnowledgeFacade knowledge,AiManagementMappers management,MemoryKnowledgeMapper mapper,MemoryPacketMapper packets,MemoryMapper memories,MemoryForgetMapper sources,AiInvokeFacade ai,PlatformTransactionManager manager){this.enabled=enabled;this.knowledge=knowledge;this.management=management;this.mapper=mapper;this.packets=packets;this.memories=memories;this.sources=sources;this.ai=ai;transaction=new TransactionTemplate(manager);}
    public record Projection(String json,List<Dependency> dependencies,long expiresAt) { public Projection{dependencies=List.copyOf(dependencies);}@Override public String toString(){return "KnowledgeProjection[refs-only]";} }
    public Projection issue(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,JsonNode request,long deadline,JsonNode context) {
        if(!enabled||!"customer-service".equals(scope.domain()))return null;
        if(!context.path("knowledgeLineageEnabled").isBoolean()||!context.path("knowledgeLineageEnabled").booleanValue())return null;
        var release=management.findRelease(request.path("agent_release_id").asText());
        if(release==null||!"ACTIVE".equals(release.releaseStatus()))throw new MemoryException("MEMORY_KNOWLEDGE_RELEASE_REQUIRED");
        var bindings=management.listKnowledgeBindings(release.agentVersionId());if(bindings.isEmpty()||bindings.size()>16)throw new MemoryException("MEMORY_KNOWLEDGE_DIRECTORY_REQUIRED");
        var documents=JSON.createArrayNode();var dependencies=new ArrayList<Dependency>();
        for(var binding:bindings) {
            var snapshot=knowledge.currentSourceSnapshot(actor,binding.knowledgeBaseId(),binding.indexReleaseId());
            for(var document:snapshot.documents()) {
                if(documents.size()>=128)throw new MemoryException("MEMORY_KNOWLEDGE_DIRECTORY_LIMIT");
                String version=MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(snapshot.knowledgeBaseId(),snapshot.indexReleaseId(),document.documentId(),document.documentVersionId(),document.fileSha256())));
                b(executionId);
                String objectRef=binding.knowledgeBaseId()+":"+MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(scope.userId(),scope.sessionId(),executionId)));
                String id=UUID.nameUUIDFromBytes(("knowledge/1\u0000"+scope.tenantId()+"\u0000"+scope.userId()+"\u0000"+scope.sessionId()+"\u0000"+executionId+"\u0000"+version).getBytes(StandardCharsets.UTF_8)).toString();
                var source=packets.findSource(b(scope.tenantId()),b(id));
                if(source==null){one(mapper.insertSource(b(scope.tenantId()),b(id),b(objectRef),b(version),Instant.ofEpochSecond(deadline)));source=packets.findSource(b(scope.tenantId()),b(id));}
                if(source==null||source.blocked()||source.deletionEpoch()>0||!Arrays.equals(source.sourceVersion(),b(version)))throw new MemoryException("MEMORY_SOURCE_CHANGED");
                var dependency=new Dependency("KNOWLEDGE_DOCUMENT",id,version,source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch());dependencies.add(dependency);
                var entry=documents.addObject();entry.put("knowledge_base_id",snapshot.knowledgeBaseId());entry.put("index_release_id",snapshot.indexReleaseId());entry.put("document_id",document.documentId());entry.put("document_version_id",document.documentVersionId());entry.put("file_sha256",document.fileSha256());entry.set("source",JSON.valueToTree(dependency));
            }
        }
        if(documents.isEmpty())throw new MemoryException("MEMORY_KNOWLEDGE_DIRECTORY_REQUIRED");
        var root=JSON.createObjectNode();root.put("schema_version","knowledge-context/1");root.put("tenant_id",scope.tenantId());root.put("user_id",scope.userId());root.set("documents",documents);
        return new Projection(root.toString(),MemoryPacketDigest.dependencies(dependencies),deadline);
    }
    public String hydrate(IdentityFacade.Subject actor,MemoryScopeDTO scope,String wire) {
        if(!enabled)throw new MemoryException("MEMORY_KNOWLEDGE_FEATURE_DISABLED");
        try {
            var root=JSON.readTree(wire);if(!scope.tenantId().equals(root.path("tenant_id").asText())||!scope.userId().equals(root.path("user_id").asText()))throw new MemoryException("MEMORY_SCOPE_DENIED");
            var snapshots=new HashMap<String,com.aiep.knowledge.api.KnowledgeSourceSnapshot>();
            for(var document:root.path("documents")) {
                String kb=document.path("knowledge_base_id").asText(),release=document.path("index_release_id").asText();
                var snapshot=snapshots.computeIfAbsent(kb+"/"+release,key->knowledge.currentSourceSnapshot(actor,kb,release));
                if(snapshot.documents().stream().noneMatch(d->d.documentId().equals(document.path("document_id").asText())&&d.documentVersionId().equals(document.path("document_version_id").asText())&&d.fileSha256().equals(document.path("file_sha256").asText())))throw new MemoryException("MEMORY_SOURCE_CHANGED");
            }return wire;
        }catch(java.io.IOException invalid){throw new MemoryException("MEMORY_KNOWLEDGE_DIRECTORY_INVALID");}
    }
    /** 授权目录的撤销映射与模型实际见到的EXECUTION/Manifest闭包分开。 */
    public void recordAuthority(MemoryScopeDTO scope,String execution,Projection directory) {
        for(var source:directory.dependencies())one(packets.insertDependency(b(scope.tenantId()),b(source.sourceId()),"KNOWLEDGE_SCOPE",b(execution),b("1"),b(execution),source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch()));
    }
    /** 知识拥有者持久event由Facade取出；只推进本域source/outbox，不跨模块SQL。 */
    public void applyEvent(com.aiep.knowledge.api.KnowledgeSourceEvent event) {
        int claimed=mapper.claimEvent(b(event.tenantId()),b(event.eventId()));if(claimed==0)return;if(claimed!=1)throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
        for(var source:mapper.listSources(b(event.tenantId()),b(event.knowledgeBaseId()))) {
            one(mapper.revoke(b(event.tenantId()),source.id()));memories.advanceTombstone(b(event.tenantId()),"SOURCE",source.id(),source.deletionEpoch()+1,source.grantEpoch()+1,source.sourceEpoch()+1);
            one(memories.insertOutbox(b(event.tenantId()),UUID.nameUUIDFromBytes((event.eventId()+new String(source.id(),StandardCharsets.UTF_8)).getBytes(StandardCharsets.UTF_8)).toString().getBytes(StandardCharsets.UTF_8),source.id(),b("knowledge"),"KNOWLEDGE_SOURCE_REVOKED",source.deletionEpoch()+1));
        }
    }
    @Scheduled(fixedDelayString="${aiep.memory.knowledge-source-scan-delay-ms:60000}") public void dispatchSourceEvents() {
        if(!enabled)return;
        for(var event:knowledge.pendingSourceEvents(16)) {
            transaction.executeWithoutResult(tx->applyEvent(event));knowledge.acknowledgeSourceEvent(event.eventId());
        }
        for(var delivery:mapper.due()) {
            byte[] token=b(UUID.randomUUID().toString());if(!Boolean.TRUE.equals(transaction.execute(tx->mapper.claim(delivery,token)==1)))continue;
            boolean success=false;try{success=cleanup(delivery);}catch(RuntimeException refused){/* 有界持久补偿，未知不作已清理证明。 */}
            boolean result=success;transaction.executeWithoutResult(tx->mapper.finish(delivery,token,result));
        }
    }
    private boolean cleanup(MemoryKnowledgeMapper.DeliveryPO event) {
        var affected=transaction.execute(tx->List.copyOf(sources.listSourceDependencies(event.tenantId(),event.sourceId())));
        var executions=new TreeMap<String,List<Dependency>>();
        for(var dependency:affected) {
            if(!Set.of("EXECUTION","MESSAGE","KNOWLEDGE_SCOPE").contains(dependency.targetType()))return false;
            if(dependency.executionId()!=null&&dependency.executionId().length>0)executions.computeIfAbsent(new String(dependency.executionId(),StandardCharsets.UTF_8),unused->new ArrayList<>()).add(new Dependency(dependency.sourceType(),new String(dependency.sourceId(),StandardCharsets.UTF_8),new String(dependency.sourceVersion(),StandardCharsets.UTF_8),dependency.grantEpoch(),dependency.sourceEpoch(),dependency.deletionEpoch()));
            else if("EXECUTION".equals(dependency.targetType()))return false;
        }
        for(var entry:executions.entrySet()) {
            var packet=packets.findPacket(event.tenantId(),b(entry.getKey()));if(packet==null)return false;
            String ref="kb-cleanup-"+MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(new String(event.eventId(),StandardCharsets.UTF_8),entry.getKey())));
            var command=new MemoryCleanupRequest(ref,packet.executionRevision(),Math.max(packet.grantEpoch()+1,event.epoch()),Math.max(packet.sourceEpoch()+1,event.epoch()),Math.max(packet.deletionEpoch()+1,event.epoch()),MemoryPacketDigest.dependencies(entry.getValue()));
            var receipt=ai.cleanupMemoryExecution(new String(event.tenantId(),StandardCharsets.UTF_8),entry.getKey(),command);
            if(receipt==null||!ref.equals(receipt.eventId())||!entry.getKey().equals(receipt.executionId())||receipt.deletionEpoch()!=command.deletionEpoch())return false;
            for(String target:List.of("AGENT_STOP","THREADS","SNAPSHOT"))if(receipt.receipts().get(target)==null||!receipt.receipts().get(target).matches("[A-Za-z0-9:_-]{16,160}"))return false;
        }return true;
    }
    private static byte[] b(String value){return MemoryMapper.identity(value);}private static void one(int value){if(value!=1)throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");}
}
