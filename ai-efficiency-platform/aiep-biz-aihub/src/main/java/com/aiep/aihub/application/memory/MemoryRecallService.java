package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryIndexMapper;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemorySemanticTransport.*;
import java.time.Instant;
import java.util.*;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Agent返回引用之后再次校验当前来源/版本；不足八条不放宽授权集合。 */
@Service
public class MemoryRecallService {
    private final boolean enabled;
    private final MemoryIndexService indexes;
    private final MemoryPreferenceService preferences;
    private final AiInvokeFacade ai;
    private final TransactionTemplate transactions;
    private final MemoryMapper policies;
    public MemoryRecallService(@Value("${aiep.memory.recall-enabled:false}") boolean enabled,MemoryIndexService indexes,
            MemoryPreferenceService preferences,AiInvokeFacade ai,PlatformTransactionManager manager,MemoryMapper policies) {
        this.enabled=enabled;this.indexes=indexes;this.preferences=preferences;this.ai=ai;transactions=new TransactionTemplate(manager);
        transactions.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
        this.policies=policies;
    }
    public record RecallItem(String itemId,String versionId,long generation,String fieldKey,String value,double score) {
        @Override public String toString(){return "MemoryRecallItem[redacted]";}
    }
    public record Result(List<RecallItem> items,String queryEmbeddingStatus,String hydrationStatus) { }
    private record Frozen(Recall request,Map<Identity,MemoryIndexMapper.Job> jobs) { }
    public Result recall(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,List<String> terms) {
        return recall(actor,scope,executionId,terms,null);
    }
    public Result recall(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,List<String> terms,String query) {
        if(!enabled)throw new MemoryException("FEATURE_DISABLED");
        Frozen frozen=transactions.execute(tx->{
            var jobs=indexes.legalReady(actor,scope);var execution=indexes.execution(scope,executionId);
            var space=indexes.semanticPolicy(scope);var legal=new LinkedHashMap<Identity,MemoryIndexMapper.Job>();
            for(var job:jobs)if(MemoryIndexService.space(job).equals(space))legal.put(MemoryIndexService.identity(job),job);
            boolean embedding=query!=null;
            if(embedding) {
                var policy=policies.findPublishedPolicy(MemoryIndexService.b(scope.tenantId()),scope.domain());MemoryPolicyService.requireArtifactPolicy(policy);
                try {var setting=new ObjectMapper().readTree(policy.policyJson()).path("semantic").path("queryEmbeddingEnabled");if(!setting.isBoolean()||!setting.booleanValue())throw new MemoryException("MEMORY_QUERY_EMBEDDING_NOT_AUTHORIZED");}
                catch(java.io.IOException invalid){throw new MemoryException("MEMORY_POLICY_INVALID");}
            }
            var auth=new Authorization(MemoryIndexService.indexScope(scope),space,execution.scope(),List.copyOf(legal.keySet()),Math.min(execution.deadline(),Instant.now().getEpochSecond()+30),embedding,8);
            return new Frozen(new Recall(auth,terms,query),Map.copyOf(legal));
        });
        if(frozen.jobs().isEmpty())return new Result(List.of(),"NOT_REQUESTED","CURRENT_AUTHORIZATION_VERIFIED");
        var result=ai.recallMemory(scope.tenantId(),frozen.request());result.validate(frozen.request());
        return transactions.execute(tx->{
            indexes.requireEnabled(actor,scope);indexes.execution(scope,executionId);var items=new ArrayList<RecallItem>();int bytes=0;
            for(var candidate:result.candidates()) {
                var job=frozen.jobs().get(candidate.identity());if(job==null)throw new MemoryException("MEMORY_SCOPE_DENIED");
                try {
                    var preference=preferences.get(actor,scope,MemoryIndexService.text(job.itemId())).preference();indexes.requireCurrent(scope,job,preference);
                    int bound=preference.fieldKey().getBytes(java.nio.charset.StandardCharsets.UTF_8).length+preference.value().getBytes(java.nio.charset.StandardCharsets.UTF_8).length+256;
                    if(bytes+bound>2048)continue;bytes+=bound;
                    items.add(new RecallItem(preference.id(),preference.versionId(),job.generation(),preference.fieldKey(),preference.value(),candidate.score()));
                }catch(MemoryException stale){if(!Set.of("MEMORY_NOT_FOUND","MEMORY_SOURCE_CHANGED","MEMORY_REVISION_CONFLICT").contains(stale.code()))throw stale;}
            }
            return new Result(List.copyOf(items),result.queryEmbeddingStatus(),"CURRENT_AUTHORIZATION_VERIFIED");
        });
    }
}
