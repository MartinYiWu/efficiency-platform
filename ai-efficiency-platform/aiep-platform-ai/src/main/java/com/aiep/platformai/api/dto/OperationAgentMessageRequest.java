package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.util.List;

public record OperationAgentMessageRequest(
        @JsonProperty("contract_version") String contractVersion,
        String message,
        @JsonProperty("request_id") String requestId,
        @JsonProperty("user_id") String userId,
        List<Object> attachments,
        List<OperationAgentArtifactContext> artifacts,
        @JsonIgnore String tenantId,
        @JsonProperty("memory_context") MemoryContextEnvelope memoryContext,
        @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_EMPTY)
        List<MemoryHistoryMessage> history) {

    public OperationAgentMessageRequest {
        if (memoryContext == null) memoryContext = MemoryContextEnvelope.disabled();
        history=List.copyOf(history);
        if(history.size()>8||history.stream().mapToInt(item->item.content().length()).sum()>12000)
            throw new IllegalArgumentException("MEMORY_HISTORY_LIMIT");
    }
    public OperationAgentMessageRequest(String contractVersion,String message,String requestId,String userId,List<Object> attachments,
            List<OperationAgentArtifactContext> artifacts,String tenantId,MemoryContextEnvelope memoryContext) {
        this(contractVersion,message,requestId,userId,attachments,artifacts,tenantId,memoryContext,List.of());
    }
    public OperationAgentMessageRequest withHistory(List<MemoryHistoryMessage> history) {
        return new OperationAgentMessageRequest(contractVersion,message,requestId,userId,attachments,artifacts,tenantId,memoryContext,history);
    }

    public OperationAgentMessageRequest(String contractVersion, String message, String requestId, String userId, List<Object> attachments, List<OperationAgentArtifactContext> artifacts, String tenantId) {
        this(contractVersion, message, requestId, userId, attachments, artifacts, tenantId, MemoryContextEnvelope.disabled());
    }

    public OperationAgentMessageRequest(String message, String requestId, String userId, List<OperationAgentArtifactContext> artifacts, String tenantId, MemoryContextEnvelope memoryContext) {
        this("conversation/1", message, requestId, userId, List.of(), List.copyOf(artifacts), tenantId, memoryContext);
    }

    public OperationAgentMessageRequest(String message, String requestId, String userId, String tenantId) {
        this("conversation/1", message, requestId, userId, List.of(), List.of(), tenantId);
    }

    public OperationAgentMessageRequest(
            String message,
            String requestId,
            String userId,
            List<OperationAgentArtifactContext> artifacts,
            String tenantId) {
        this("conversation/1", message, requestId, userId, List.of(), List.copyOf(artifacts), tenantId);
    }
}
