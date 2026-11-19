package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 仅运行时内部元数据；无模型正文，无模型自报权限字段。 */
public record MemoryRuntimeManifest(@JsonProperty("runtime_id") String runtimeId,
        @JsonProperty("execution_id") String executionId, @JsonProperty("packet_id") String packetId,
        @JsonProperty("packet_revision") long packetRevision, List<Operation> manifests) {
    public MemoryRuntimeManifest { manifests=List.copyOf(manifests); }
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record Operation(Scope scope, @JsonProperty("node_id") String nodeId,
        @JsonProperty("packet_id") String packetId, @JsonProperty("packet_revision") long packetRevision,
        @JsonProperty("safety_dependencies") List<MemoryContextPacket.Dependency> safetyDependencies,
        @JsonProperty("selected_sources") List<MemoryContextPacket.Dependency> selectedSources,
        Measurement measurement, WindowDecision decision,
        @JsonProperty("cpu_before_tokens") Long cpuBeforeTokens,
        @JsonProperty("cpu_after_tokens") Long cpuAfterTokens,
        @JsonProperty("summary_before_tokens") Long summaryBeforeTokens,
        @JsonProperty("summary_after_tokens") Long summaryAfterTokens,
        @JsonProperty("summary_cas_status") String summaryCasStatus,
        @JsonProperty("summary_adoption_status") String summaryAdoptionStatus,
        @JsonProperty("output_reserve_tokens") Long outputReserveTokens,
        List<List<String>> exclusions,
        @JsonProperty("operation_id") String operationId,
        @JsonProperty("model_version") String modelVersion,
        @JsonProperty("prompt_version") String promptVersion,
        @JsonProperty("output_schema_version") String outputSchemaVersion,
        @JsonProperty("policy_version") String policyVersion,
        @JsonProperty("derive_binding_json") String deriveBindingJson) {
        public Operation { safetyDependencies=List.copyOf(safetyDependencies);selectedSources=List.copyOf(selectedSources); }
        public Operation(Scope scope,String nodeId,String packetId,long packetRevision,
                List<MemoryContextPacket.Dependency> safetyDependencies,List<MemoryContextPacket.Dependency> selectedSources,
                Measurement measurement,WindowDecision decision,Long cpuBeforeTokens,Long cpuAfterTokens,
                Long summaryBeforeTokens,Long summaryAfterTokens,String summaryCasStatus,String summaryAdoptionStatus,
                Long outputReserveTokens,List<List<String>> exclusions) {
            this(scope,nodeId,packetId,packetRevision,safetyDependencies,selectedSources,measurement,decision,cpuBeforeTokens,cpuAfterTokens,
                summaryBeforeTokens,summaryAfterTokens,summaryCasStatus,summaryAdoptionStatus,outputReserveTokens,exclusions,null,null,null,null,null,null);
        }
        public Operation(Scope scope,String nodeId,String packetId,long packetRevision,
                List<MemoryContextPacket.Dependency> safetyDependencies,List<MemoryContextPacket.Dependency> selectedSources) {
            this(scope,nodeId,packetId,packetRevision,safetyDependencies,selectedSources,null,null,null,null,null,null,null,null,null,null);
        }
    }
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record Measurement(@JsonProperty("total_upper_bound") Long totalUpperBound,String method,Boolean verified) { }
    @JsonIgnoreProperties(ignoreUnknown=true)
    public record WindowDecision(@JsonProperty("H_ctx") Long inputLimit,@JsonProperty("T") Long inputTokens,
            @JsonProperty("F") Long freeTokens,String status) { }
    public record Scope(MemoryContextEnvelope.Scope conversation,
        @JsonProperty("task_id") String taskId,@JsonProperty("execution_id") String executionId,
        @JsonProperty("subtask_id") String subtaskId,String purpose,
        @JsonProperty("execution_agent_id") String executionAgentId) { }
}
