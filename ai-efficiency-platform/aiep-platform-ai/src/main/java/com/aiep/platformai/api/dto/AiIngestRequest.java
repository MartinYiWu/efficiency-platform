package com.aiep.platformai.api.dto;

public record AiIngestRequest(AiRequestContext context, String taskId, Long knowledgeBaseId, Long documentId) {
}
