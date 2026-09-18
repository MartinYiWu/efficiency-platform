package com.aiep.platformai.api.dto;

/** Java-computed request metadata shared with the Agent. */
public record AiRequestContext(String traceId, Long userId, String sourceModule, String actionType) {
}
