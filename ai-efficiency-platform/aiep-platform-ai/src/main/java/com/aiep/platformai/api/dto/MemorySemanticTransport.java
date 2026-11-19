package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Set;

/** 索引只传有限投影，召回只返引用；Java负责当前权限二次取正文。 */
public final class MemorySemanticTransport {
    private MemorySemanticTransport() { }
    public record Scope(@JsonProperty("tenant_id") String tenantId,@JsonProperty("user_id") String userId,
            String domain,@JsonProperty("top_level_agent_id") String topLevelAgentId,
            @JsonProperty("scope_kind") String scopeKind,@JsonProperty("scope_ref") String scopeRef) {
        public Scope {
            id(tenantId);id(userId);id(scopeRef);
            if(!Set.of("operations","customer-service").contains(domain)||!domain.equals(topLevelAgentId)
                    ||!"USER_PRIVATE".equals(scopeKind)||!userId.equals(scopeRef))invalid();
        }
        public String key() {return MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(tenantId,userId,domain,topLevelAgentId,scopeKind,scopeRef)));}
    }
    public record Space(@JsonProperty("embedding_model") String embeddingModel,int dimension,
            @JsonProperty("policy_version") String policyVersion) {
        public Space {id(embeddingModel);id(policyVersion);if(dimension<1||dimension>4096)invalid();}
    }
    public record Identity(@JsonProperty("item_id") String itemId,@JsonProperty("version_id") String versionId,
            long generation,@JsonProperty("deletion_epoch") long deletionEpoch,
            @JsonProperty("source_fingerprint") String sourceFingerprint) {
        public Identity {id(itemId);id(versionId);if(generation<1||deletionEpoch<0)invalid();digest(sourceFingerprint);}
    }
    public record Upsert(@JsonProperty("event_id") String eventId,Scope scope,Space space,Identity identity,
            MemoryRuntimeManifest.Scope execution,@JsonProperty("expires_at") long expiresAt,String projection,List<String> terms,
            @JsonProperty("retention_expires_at") long retentionExpiresAt) {
        public Upsert {id(eventId);bound(scope,execution);if(space==null||identity==null||expiresAt<1||retentionExpiresAt<expiresAt||projection==null||projection.isBlank()||projection.codePointCount(0,projection.length())>8192)invalid();terms=MemorySemanticTransport.terms(terms);}
        @Override public String toString(){return "MemoryIndexUpsert[redacted]";}
    }
    public record Delete(@JsonProperty("event_id") String eventId,Scope scope,@JsonProperty("item_id") String itemId,
            long generation,@JsonProperty("deletion_epoch") long deletionEpoch) {
        public Delete {id(eventId);id(itemId);if(scope==null||generation<0||deletionEpoch<0)invalid();}
    }
    public record Receipt(@JsonProperty("event_id") String eventId,@JsonProperty("scope_key") String scopeKey,
            @JsonProperty("item_id") String itemId,@JsonProperty("version_id") String versionId,
            long generation,@JsonProperty("deletion_epoch") long deletionEpoch,String state) {
        public void validate(Upsert request){if(!eventId.equals(request.eventId)||!scopeKey.equals(request.scope.key())||!itemId.equals(request.identity.itemId)||!java.util.Objects.equals(versionId,request.identity.versionId)||generation!=request.identity.generation||deletionEpoch!=request.identity.deletionEpoch||!"READY".equals(state))invalid();}
        public void validate(Delete request){if(!eventId.equals(request.eventId)||!scopeKey.equals(request.scope.key())||!itemId.equals(request.itemId)||versionId!=null||generation!=request.generation||deletionEpoch!=request.deletionEpoch||!"DELETED".equals(state))invalid();}
    }
    public record Authorization(Scope scope,Space space,MemoryRuntimeManifest.Scope execution,List<Identity> allowed,
            @JsonProperty("expires_at") long expiresAt,@JsonProperty("query_embedding_allowed") boolean queryEmbeddingAllowed,
            @JsonProperty("top_k") int topK) {
        public Authorization {bound(scope,execution);if(space==null||allowed==null||allowed.size()>10000||expiresAt<1||topK<1||topK>8)invalid();allowed=List.copyOf(allowed);if(allowed.stream().map(Identity::itemId).distinct().count()!=allowed.size())invalid();}
    }
    public record Recall(Authorization authorization,List<String> terms,String query) {
        public Recall {if(authorization==null||(query==null)!=!authorization.queryEmbeddingAllowed||query!=null&&(query.isBlank()||query.codePointCount(0,query.length())>2048))invalid();terms=MemorySemanticTransport.terms(terms);}
    }
    public record Candidate(Identity identity,double score){public Candidate{if(identity==null||!Double.isFinite(score))invalid();}}
    public record RecallResult(List<Candidate> candidates,@JsonProperty("query_embedding_status") String queryEmbeddingStatus,
            @JsonProperty("legal_count") int legalCount,@JsonProperty("elapsed_ms") double elapsedMs,
            @JsonProperty("hydration_required") boolean hydrationRequired) {
        public RecallResult{if(candidates==null||candidates.size()>8||legalCount<0||legalCount>10000||!Double.isFinite(elapsedMs)||elapsedMs<0||!hydrationRequired||!Set.of("NOT_REQUESTED","USED").contains(queryEmbeddingStatus))invalid();candidates=List.copyOf(candidates);}
        public void validate(Recall request){if(legalCount!=request.authorization.allowed.size()||candidates.size()>request.authorization.topK||"USED".equals(queryEmbeddingStatus)&&!request.authorization.queryEmbeddingAllowed||candidates.stream().map(c->c.identity.itemId).distinct().count()!=candidates.size()||candidates.stream().anyMatch(c->!request.authorization.allowed.contains(c.identity)))invalid();}
    }
    private static final com.fasterxml.jackson.databind.ObjectMapper JSON=new com.fasterxml.jackson.databind.ObjectMapper();
    private static List<String> terms(List<String> values){if(values==null||values.size()>32||values.stream().anyMatch(v->v==null||v.isBlank()||v.codePointCount(0,v.length())>128))invalid();return List.copyOf(values);}
    private static void bound(Scope scope,MemoryRuntimeManifest.Scope execution){if(scope==null||execution==null||execution.conversation()==null)invalid();var c=execution.conversation();if(!scope.tenantId.equals(c.tenantId())||!scope.userId.equals(c.userId())||!scope.domain.equals(c.domain())||!scope.topLevelAgentId.equals(c.topLevelAgentId()))invalid();for(String v:List.of(execution.taskId(),execution.executionId(),execution.subtaskId(),execution.purpose(),execution.executionAgentId()))id(v);}
    private static void id(String value){if(value==null||value.isBlank()||value.codePointCount(0,value.length())>128||value.codePoints().anyMatch(cp->cp>=0xd800&&cp<=0xdfff))invalid();}
    private static void digest(String value){if(value==null||!value.matches("[0-9a-f]{64}"))invalid();}
    private static void invalid(){throw new IllegalArgumentException("MEMORY_SEMANTIC_CONTRACT_INVALID");}
}
