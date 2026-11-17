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
        @JsonProperty("selected_sources") List<MemoryContextPacket.Dependency> selectedSources) {
        public Operation { safetyDependencies=List.copyOf(safetyDependencies);selectedSources=List.copyOf(selectedSources); }
    }
    public record Scope(MemoryContextEnvelope.Scope conversation,
        @JsonProperty("task_id") String taskId,@JsonProperty("execution_id") String executionId,
        @JsonProperty("subtask_id") String subtaskId,String purpose,
        @JsonProperty("execution_agent_id") String executionAgentId) { }
}
