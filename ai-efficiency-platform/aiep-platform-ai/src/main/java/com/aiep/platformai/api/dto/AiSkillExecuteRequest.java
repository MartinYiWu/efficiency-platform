package com.aiep.platformai.api.dto;

public record AiSkillExecuteRequest(AiRequestContext context, Long skillId, String input) {
}
