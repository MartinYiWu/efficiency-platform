package com.aiep.platformai.api.dto;

public record AiSkillExecuteRequest(AiRequestContext context, Long skillId, String input,
        @com.fasterxml.jackson.annotation.JsonIgnore String tenantId) {
    public AiSkillExecuteRequest(AiRequestContext context, Long skillId, String input) { this(context, skillId, input, null); }
}
