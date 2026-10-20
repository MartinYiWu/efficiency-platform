package com.aiep.aihub.repository.management;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public final class AiManagementPOs {
    private AiManagementPOs() {
    }

    public record AgentDefinitionPO(
            String id, String agentKey, String name, String description, String agentType,
            String status, String createdBy, LocalDateTime createdAt,
            String updatedBy, LocalDateTime updatedAt) { }

    public record AgentVersionPO(
            String id, String agentDefinitionId, String semanticVersion, String graphKey,
            String graphVersion, String status, String changeSummary, String createdBy,
            LocalDateTime createdAt, LocalDateTime publishedAt) { }

    public record PromptDefinitionPO(
            String id, String promptKey, String scope, String ownerAgentDefinitionId,
            String name, String description, String stageKey, String status,
            String createdBy, LocalDateTime createdAt, String updatedBy, LocalDateTime updatedAt) { }

    public record PromptVersionPO(
            String id, String promptDefinitionId, String semanticVersion, String status,
            String checksum, String changeSummary, String createdBy,
            LocalDateTime createdAt, LocalDateTime publishedAt) { }

    public record PromptMessageTemplatePO(
            String id, String promptVersionId, int ordinal, String role, String messageKey,
            String contentTemplate, String contentFormat, boolean trustedInstruction,
            String checksum) { }

    public record PromptVariablePO(
            String id, String promptMessageTemplateId, String variableName, String valueType,
            String valueSource, boolean required, boolean sensitive, Integer maxLength,
            boolean allowUntrustedContent) { }

    public record PromptBindingPO(
            String agentVersionId, String stageKey, int ordinal, String promptDefinitionId,
            String promptVersionId, boolean required) { }

    public record AgentVersionPolicyBindingPO(
            String agentVersionId, String modelPolicyId, String ragPolicyId) { }

    public record AgentVersionKnowledgeBindingPO(
            String agentVersionId, String knowledgeBaseId, String indexReleaseId,
            int priority, boolean required) { }

    public record ModelPolicyPO(
            String id, String ownerAgentDefinitionId, String policyKey, String semanticVersion,
            String provider, String modelName, BigDecimal temperature, BigDecimal topP,
            int maxInputTokens, int maxOutputTokens, int connectTimeoutMs, int readTimeoutMs,
            int maxRetries, String status, String checksum, String createdBy,
            LocalDateTime createdAt, LocalDateTime publishedAt) { }

    public record RagPolicyPO(
            String id, String ownerAgentDefinitionId, String policyKey, String semanticVersion,
            int rewriteQueryLimit, int vectorTopK, int ftsTopK, int fusionTopK,
            int rerankTopK, int contextTokenLimit, int citationLimit, String status,
            String checksum, String createdBy, LocalDateTime createdAt,
            LocalDateTime publishedAt) { }
}
