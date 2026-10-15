package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record OperationAgentRunEvent(
        @JsonProperty("contract_version") String contractVersion,
        String event,
        @JsonProperty("run_id") String runId,
        long sequence,
        Map<String, Object> payload) {
}
