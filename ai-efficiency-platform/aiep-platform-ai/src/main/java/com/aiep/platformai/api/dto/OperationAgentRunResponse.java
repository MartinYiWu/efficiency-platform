package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OperationAgentRunResponse(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("conversation_id") String conversationId,
        @JsonProperty("turn_id") String turnId,
        @JsonProperty("run_id") String runId,
        String status) {
}
