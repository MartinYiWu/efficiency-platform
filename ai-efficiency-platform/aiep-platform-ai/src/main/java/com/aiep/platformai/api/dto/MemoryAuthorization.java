package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** Java发布的原执行授权，不允许模型补写或扩展。 */
public record MemoryAuthorization(Policy policy,
        @JsonProperty("execution_grants") List<ExecutionGrant> executionGrants,
        @JsonProperty("deadline_epoch_seconds") long deadlineEpochSeconds,
        @JsonProperty("packet_digest") String packetDigest,
        @JsonProperty("semantic_snapshot_digest") String semanticSnapshotDigest,
        @JsonProperty("request_digest") String requestDigest,
        @JsonProperty("input_dependencies") List<MemoryContextPacket.Dependency> inputDependencies,
        @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
        @JsonProperty("summary_context_json") String summaryContextJson,
        @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
        @JsonProperty("derive_template_json") String deriveTemplateJson,
        @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
        @JsonProperty("knowledge_context_json") String knowledgeContextJson) {
    public MemoryAuthorization(Policy policy,List<ExecutionGrant> grants,long deadline,String digest,String semantic,String request,List<MemoryContextPacket.Dependency> inputDependencies,String summaryContextJson,String deriveTemplateJson) {
        this(policy,grants,deadline,digest,semantic,request,inputDependencies,summaryContextJson,deriveTemplateJson,null);
    }
    public MemoryAuthorization(Policy policy,List<ExecutionGrant> grants,long deadline,String digest,String semantic,String request,List<MemoryContextPacket.Dependency> inputDependencies,String summaryContextJson) {
        this(policy,grants,deadline,digest,semantic,request,inputDependencies,summaryContextJson,null);
    }
    public MemoryAuthorization(Policy policy,List<ExecutionGrant> grants,long deadline,String digest,String semantic,String request,List<MemoryContextPacket.Dependency> inputDependencies) {
        this(policy,grants,deadline,digest,semantic,request,inputDependencies,null);
    }
    public MemoryAuthorization(Policy policy,List<ExecutionGrant> grants,long deadline,String digest,String semantic,String request) {
        this(policy,grants,deadline,digest,semantic,request,List.of());
    }
    public MemoryAuthorization {
        inputDependencies=List.copyOf(inputDependencies);
        executionGrants = List.copyOf(executionGrants);
        if(summaryContextJson!=null&&(summaryContextJson.isBlank()||summaryContextJson.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>524288))throw new IllegalArgumentException("MEMORY_SUMMARY_CONTEXT_INVALID");
        if(deriveTemplateJson!=null&&(deriveTemplateJson.isBlank()||deriveTemplateJson.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>524288))throw new IllegalArgumentException("MEMORY_SUMMARY_CONTEXT_INVALID");
        if(knowledgeContextJson!=null&&(knowledgeContextJson.isBlank()||knowledgeContextJson.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>524288))throw new IllegalArgumentException("MEMORY_KNOWLEDGE_CONTEXT_INVALID");
        if (policy == null || !policy.enabled() || executionGrants.isEmpty() || deadlineEpochSeconds <= 0
                || executionGrants.stream().map(ExecutionGrant::nodeId).distinct().count() != executionGrants.size()
                || executionGrants.stream().anyMatch(grant -> !policy.agentIds().contains(grant.executionAgentId())))
            throw new IllegalArgumentException("MEMORY_AUTHORIZATION_INVALID");
        for (String digest : new String[]{packetDigest, semanticSnapshotDigest, requestDigest})
            if (digest == null || !digest.matches("[0-9a-f]{64}")) throw new IllegalArgumentException("MEMORY_DIGEST_INVALID");
    }
    public record ExecutionGrant(@JsonProperty("node_id") String nodeId,
            @JsonProperty("execution_agent_id") String executionAgentId, String purpose) {
        public ExecutionGrant { MemoryContextPacket.requireId(nodeId); MemoryContextPacket.requireId(executionAgentId); MemoryContextPacket.requireId(purpose); }
    }
    public record Policy(@JsonProperty("policy_id") String policyId, String version, String domain,
            @JsonProperty("agent_ids") List<String> agentIds, boolean enabled,
            @JsonProperty("readable_layers") List<String> readableLayers,
            @JsonProperty("writable_kinds") List<String> writableKinds,
            @JsonProperty("allowed_scopes") List<String> allowedScopes,
            @JsonProperty("field_allowlist") List<String> fieldAllowlist,
            @JsonProperty("sensitivity_levels") List<String> sensitivityLevels,
            @JsonProperty("confirmation_required") boolean confirmationRequired,
            @JsonProperty("auto_extract") boolean autoExtract,
            @JsonProperty("shared_approval_required") boolean sharedApprovalRequired,
            @JsonProperty("source_types") List<String> sourceTypes,
            @JsonProperty("retention_days") int retentionDays,
            @JsonProperty("recall_top_k") int recallTopK,
            @JsonProperty("recall_token_limit") int recallTokenLimit,
            @JsonProperty("max_paid_operations") int maxPaidOperations,
            @JsonProperty("degradation_mode") String degradationMode,
            @JsonProperty("source_deletion_mode") String sourceDeletionMode,
            @JsonProperty("schema_version") String schemaVersion,
            @JsonProperty("model_version") String modelVersion,
            @JsonProperty("tokenizer_version") String tokenizerVersion) {
        public Policy {
            agentIds = List.copyOf(agentIds); readableLayers = List.copyOf(readableLayers);
            writableKinds = List.copyOf(writableKinds); allowedScopes = List.copyOf(allowedScopes);
            fieldAllowlist = List.copyOf(fieldAllowlist); sensitivityLevels = List.copyOf(sensitivityLevels);
            sourceTypes = List.copyOf(sourceTypes);
        }
    }
}
