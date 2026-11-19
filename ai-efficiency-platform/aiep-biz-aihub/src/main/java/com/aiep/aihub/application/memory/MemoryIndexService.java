package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryIndexMapper.Job;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.aiep.platformai.api.dto.MemorySemanticTransport.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 明确请求才建立有限索引Job；事务外只发送一次，未知结果不会自动重新扣费。 */
@Service
public class MemoryIndexService {
    private static final ObjectMapper JSON=new ObjectMapper();
    private final boolean enabled;
    private final MemoryIndexMapper mapper;
    private final MemoryMapper memories;
    private final MemoryPacketMapper packets;
    private final MemoryPreferenceService preferences;
    private final MemoryScopePolicy scopes;
    private final MemoryDependencyService dependencies;
    private final AiInvokeFacade ai;
    private final TransactionTemplate transactions;
    public MemoryIndexService(@Value("${aiep.memory.index-enabled:false}") boolean enabled,MemoryIndexMapper mapper,
            MemoryMapper memories,MemoryPacketMapper packets,MemoryPreferenceService preferences,MemoryScopePolicy scopes,
            MemoryDependencyService dependencies,AiInvokeFacade ai,PlatformTransactionManager manager) {
        this.enabled=enabled;this.mapper=mapper;this.memories=memories;this.packets=packets;this.preferences=preferences;
        this.scopes=scopes;this.dependencies=dependencies;this.ai=ai;transactions=new TransactionTemplate(manager);
        transactions.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    public record IndexStatus(String id,String itemId,String versionId,long generation,String status) { }
    public IndexStatus request(IdentityFacade.Subject actor,MemoryScopeDTO scope,String itemId,long expectedRevision,String executionId,String idempotencyKey) {
        requireEnabled(actor,scope);b(itemId);b(executionId);b(idempotencyKey);
        Job job=transactions.execute(tx->{
            var preference=preferences.get(actor,scope,itemId).preference();
            if(preference.revision()!=expectedRevision)throw failure("MEMORY_REVISION_CONFLICT");
            var execution=execution(scope,executionId);var semantic=semanticPolicy(scope);
            var closure=dependencies.dependencies(scope,"MEMORY_VERSION",itemId,preference.versionId());
            if(closure.isEmpty()||!execution.dependencies().containsAll(closure))throw failure("MEMORY_SOURCE_CHANGED");
            long expires=Math.min(preference.expiresAt().getEpochSecond(),dependencies.requireCurrent(scope,closure).getEpochSecond());
            var identity=identity(itemId,preference.versionId(),expectedRevision,closure);
            String fingerprint=MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(scope,itemId,preference.versionId(),expectedRevision,executionId,semantic,identity)));
            var prior=mapper.requested(b(scope.tenantId()),b(idempotencyKey));
            if(prior!=null){if(!prior.requestFingerprint().equals(fingerprint)||!Arrays.equals(prior.userId(),b(actor.userId())))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return prior;}
            var row=new Job(b(scope.tenantId()),b(UUID.randomUUID().toString()),b(actor.userId()),scope.domain(),b(itemId),b(preference.versionId()),identity.generation(),identity.deletionEpoch(),identity.sourceFingerprint(),semantic.embeddingModel(),semantic.dimension(),semantic.policyVersion(),b(executionId),b(execution.scope().taskId()),json(execution.scope()),Instant.ofEpochSecond(expires),"QUEUED",b(idempotencyKey),fingerprint);
            one(mapper.insert(row));one(memories.insertOutbox(row.tenantId(),row.id(),row.itemId(),row.versionId(),"MEMORY_INDEX_REQUESTED",row.deletionEpoch()));return row;
        });
        if(!"QUEUED".equals(job.state()))return status(job);
        Upsert request=transactions.execute(tx->{
            var current=mapper.find(job.tenantId(),job.id());if(!"QUEUED".equals(current.state()))return null;
            var preference=preferences.get(actor,scope,itemId).preference();requireCurrent(scope,current,preference);
            var live=execution(scope,executionId);if(!live.scope().taskId().equals(text(current.taskId())))throw failure("MEMORY_EXECUTION_CONFLICT");
            one(mapper.transition(current.tenantId(),current.id(),"QUEUED","SENDING"));
            return new Upsert(text(current.id()),indexScope(scope),space(current),identity(current),live.scope(),Math.min(live.deadline(),current.expiresAt().getEpochSecond()),preference.value(),List.of(preference.value()),current.expiresAt().getEpochSecond());
        });
        if(request==null)return transactions.execute(tx->status(mapper.find(job.tenantId(),job.id())));
        try {
            var receipt=ai.upsertMemoryIndex(scope.tenantId(),request);receipt.validate(request);
            return transactions.execute(tx->{
                var current=mapper.find(job.tenantId(),job.id());
                requireCurrent(scope,current,preferences.get(actor,scope,itemId).preference());
                one(mapper.transition(current.tenantId(),current.id(),"SENDING","READY"));mapper.completeOutbox(current.tenantId(),current.id());
                return new IndexStatus(text(current.id()),text(current.itemId()),text(current.versionId()),current.generation(),"READY");
            });
        } catch(RuntimeException error) {
            transactions.executeWithoutResult(tx->mapper.transition(job.tenantId(),job.id(),"SENDING","UNKNOWN"));throw error;
        }
    }
    public IndexStatus get(IdentityFacade.Subject actor,MemoryScopeDTO scope,String jobId) {
        requireEnabled(actor,scope);return transactions.execute(tx->{var row=mapper.find(b(scope.tenantId()),b(jobId));if(row==null||!Arrays.equals(row.userId(),b(actor.userId()))||!row.domain().equals(scope.domain()))throw failure("MEMORY_NOT_FOUND");return status(row);});
    }
    List<Job> legalReady(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        requireEnabled(actor,scope);var result=new ArrayList<Job>();
        var rows=mapper.ready(b(scope.tenantId()),b(scope.userId()),scope.domain());if(rows.size()>10000)throw failure("MEMORY_RECALL_SET_LIMIT");
        var seen=new HashSet<String>();
        for(var row:rows){
            try{var preference=preferences.get(actor,scope,text(row.itemId())).preference();requireCurrent(scope,row,preference);if(seen.add(preference.id()))result.add(row);}
            catch(MemoryException stale){if(!Set.of("MEMORY_NOT_FOUND","MEMORY_SOURCE_CHANGED","MEMORY_REVISION_CONFLICT").contains(stale.code()))throw stale;}
        }
        return List.copyOf(result);
    }
    void requireCurrent(MemoryScopeDTO scope,Job job,Preference preference) {
        if(!text(job.userId()).equals(scope.userId())||!job.domain().equals(scope.domain())||!text(job.itemId()).equals(preference.id())||!text(job.versionId()).equals(preference.versionId())||job.generation()!=preference.revision()||!job.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SOURCE_CHANGED");
        var closure=dependencies.dependencies(scope,"MEMORY_VERSION",preference.id(),preference.versionId());dependencies.requireCurrent(scope,closure);
        if(!identity(job).equals(identity(preference.id(),preference.versionId(),preference.revision(),closure)))throw failure("MEMORY_SOURCE_CHANGED");
        if(!space(job).equals(semanticPolicy(scope)))throw failure("MEMORY_SOURCE_CHANGED");
    }
    record BoundExecution(MemoryRuntimeManifest.Scope scope,long deadline,List<MemoryContextPacket.Dependency> dependencies) { }
    BoundExecution execution(MemoryScopeDTO scope,String executionId) {
        var row=packets.findPacket(b(scope.tenantId()),b(executionId));if(row==null||!Arrays.equals(row.userId(),b(scope.userId()))||Instant.now().getEpochSecond()>=Math.min(row.originalDeadline(),row.expiresAt()))throw failure("MEMORY_EXECUTION_EXPIRED");
        try {
            var conversation=JSON.readValue(row.scopeJson(),MemoryContextEnvelope.Scope.class);
            if(!JSON.valueToTree(conversation).equals(JSON.valueToTree(scope)))throw failure("MEMORY_SCOPE_DENIED");
            var grants=JSON.readValue(row.grantsJson(),new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
            String originalNode=scope.domain().equals("customer-service")?"customer-service:answer_general":"direct";
            var grant=grants.stream().filter(g->g.nodeId().equals(originalNode)&&g.executionAgentId().equals(scope.topLevelAgentId())&&g.purpose().equals("assistant_response")).findFirst().orElseThrow(()->failure("MEMORY_INDEX_EXECUTION_UNSUPPORTED"));
            var closure=JSON.readValue(row.dependenciesJson(),new TypeReference<List<MemoryContextPacket.Dependency>>(){});dependencies.requireCurrent(scope,closure);
            return new BoundExecution(new MemoryRuntimeManifest.Scope(conversation,text(row.taskId()),executionId,grant.nodeId(),grant.purpose(),grant.executionAgentId()),Math.min(row.originalDeadline(),row.expiresAt()),closure);
        }catch(java.io.IOException invalid){throw failure("MEMORY_STORAGE_UNAVAILABLE");}
    }
    Space semanticPolicy(MemoryScopeDTO scope) {
        var policy=memories.findPublishedPolicy(b(scope.tenantId()),scope.domain());MemoryPolicyService.requireArtifactPolicy(policy);
        try {var root=JSON.readTree(policy.policyJson());MemoryPolicyService.requireProvisionedIndex(root);var config=root.path("semantic");if(!config.path("enabled").isBoolean()||!config.path("enabled").booleanValue()||!config.path("dimension").isIntegralNumber())throw failure("FEATURE_DISABLED");return new Space(config.path("embeddingModel").textValue(),config.path("dimension").intValue(),text(policy.versionId()));}
        catch(java.io.IOException|IllegalArgumentException invalid){throw failure("MEMORY_POLICY_INVALID");}
    }
    void requireEnabled(IdentityFacade.Subject actor,MemoryScopeDTO scope){if(!enabled)throw failure("FEATURE_DISABLED");if(scope==null||"hr".equals(scope.domain()))throw failure("MEMORY_SCOPE_DENIED");scopes.require(actor,scope,Set.of());}
    static Identity identity(String item,String version,long generation,List<MemoryContextPacket.Dependency> closure){if(closure.isEmpty())throw failure("MEMORY_SOURCE_CHANGED");return new Identity(item,version,generation,closure.stream().mapToLong(MemoryContextPacket.Dependency::deletionEpoch).max().orElseThrow(),MemoryPacketDigest.canonicalDigest(JSON.valueToTree(MemoryPacketDigest.dependencies(closure))));}
    static Identity identity(Job row){return new Identity(text(row.itemId()),text(row.versionId()),row.generation(),row.deletionEpoch(),row.sourceFingerprint());}
    static Space space(Job row){return new Space(row.embeddingModel(),row.dimension(),row.policyVersion());}
    static Scope indexScope(MemoryScopeDTO scope){return new Scope(scope.tenantId(),scope.userId(),scope.domain(),scope.topLevelAgentId(),"USER_PRIVATE",scope.userId());}
    private static IndexStatus status(Job row){return new IndexStatus(text(row.id()),text(row.itemId()),text(row.versionId()),row.generation(),row.state());}
    static String json(Object value){try{return JSON.writeValueAsString(value);}catch(java.io.IOException invalid){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static byte[] b(String value){return MemoryMapper.identity(value);}static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}static MemoryException failure(String code){return new MemoryException(code);}private static void one(int rows){if(rows!=1)throw failure("MEMORY_REVISION_CONFLICT");}
}
