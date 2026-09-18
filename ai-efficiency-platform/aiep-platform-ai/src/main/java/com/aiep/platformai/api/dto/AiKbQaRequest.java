package com.aiep.platformai.api.dto;

import java.util.List;

public record AiKbQaRequest(AiRequestContext context, List<Long> knowledgeBaseIds, String question) {
}
