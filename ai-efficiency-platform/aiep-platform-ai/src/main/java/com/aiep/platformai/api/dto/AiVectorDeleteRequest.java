package com.aiep.platformai.api.dto;

import java.util.List;

public record AiVectorDeleteRequest(AiRequestContext context, List<Long> knowledgeBaseIds, List<Long> documentIds) {
}
