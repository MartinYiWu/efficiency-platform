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
        @JsonIgnore String tenantId) {

    public OperationAgentMessageRequest(String message, String requestId, String userId, String tenantId) {
        this("conversation/1", message, requestId, userId, List.of(), tenantId);
    }
}
