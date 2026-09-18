package com.aiep.platformai.api.dto;

public record AiStreamRequest(AiRequestContext context, String sessionId, String input) {
}
