package com.aiep.aihub.management;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.aihub.application.management.AiAgentManagementService;
import com.aiep.aihub.application.management.AiManagementException;
import com.aiep.aihub.application.management.AiPolicyManagementService;
import com.aiep.aihub.application.management.AiPromptManagementService;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class AiAssetOwnershipTest {
    private static final LocalDateTime NOW = LocalDateTime.of(2026, 10, 20, 12, 0);
    private final AiManagementMappers repository = mock(AiManagementMappers.class);

    @Test
    void sharedPromptHasNoOwnerAndCanBindToAnyAgent() {
        when(repository.findAgentVersion("agent-version-1"))
                .thenReturn(agentVersion("agent-1", "DRAFT"));
        when(repository.findPromptVersion("prompt-version-1"))
                .thenReturn(promptVersion("prompt-1", "PUBLISHED"));
        when(repository.findPromptDefinition("prompt-1"))
                .thenReturn(prompt("SHARED", null));
        AiPromptManagementService service = new AiPromptManagementService(repository);

        service.bind("agent-version-1", "prompt-version-1", "safety", 1, true);

        verify(repository).insertPromptBinding(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void privatePromptCannotBindAcrossAgents() {
        when(repository.findAgentVersion("agent-version-1"))
                .thenReturn(agentVersion("agent-1", "DRAFT"));
        when(repository.findPromptVersion("prompt-version-1"))
                .thenReturn(promptVersion("prompt-1", "PUBLISHED"));
        when(repository.findPromptDefinition("prompt-1"))
                .thenReturn(prompt("PRIVATE", "agent-2"));

        assertThatThrownBy(() -> new AiPromptManagementService(repository)
                .bind("agent-version-1", "prompt-version-1", "answer", 1, true))
                .isInstanceOf(AiManagementException.class)
                .extracting("code")
                .isEqualTo("AI_ASSET_OWNER_MISMATCH");
    }

    @Test
    void releasedVersionsAreImmutableAndStateTransitionsAreOrdered() {
        when(repository.findAgentVersion("released"))
                .thenReturn(agentVersion("agent-1", "RELEASED"));
        when(repository.findAgentVersion("draft"))
                .thenReturn(agentVersion("agent-1", "DRAFT"));
        AiAgentManagementService service = new AiAgentManagementService(repository);

        assertThatThrownBy(() -> service.updateDraft(
                "released", "1.1.0", "customer-service", "2", "修改"))
                .isInstanceOf(AiManagementException.class)
                .extracting("code")
                .isEqualTo("AI_ASSET_IMMUTABLE");

        assertThat(service.transition("draft", "VALIDATED").status())
                .isEqualTo("VALIDATED");
        verify(repository).updateAgentVersion(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void modelAndRagPoliciesArePrivateToTheirAgent() {
        when(repository.findModelPolicy("model-1")).thenReturn(modelPolicy("agent-2"));
        AiPolicyManagementService service = new AiPolicyManagementService(repository);

        assertThatThrownBy(() -> service.getModelPolicy("agent-1", "model-1"))
                .isInstanceOf(AiManagementException.class)
                .extracting("code")
                .isEqualTo("AI_ASSET_OWNER_MISMATCH");
    }

    private static AgentVersionPO agentVersion(String owner, String status) {
        return new AgentVersionPO(
                status.toLowerCase(), owner, "1.0.0", "customer-service", "1",
                status, "初始版本", "1", NOW, null);
    }

    private static PromptDefinitionPO prompt(String scope, String owner) {
        return new PromptDefinitionPO(
                "prompt-1", "prompt.key", scope, owner, "Prompt", null,
                "safety", "ACTIVE", "1", NOW, "1", NOW);
    }

    private static PromptVersionPO promptVersion(String definitionId, String status) {
        return new PromptVersionPO(
                "prompt-version-1", definitionId, "1.0.0", status,
                "a".repeat(64), "初始版本", "1", NOW, null);
    }

    private static ModelPolicyPO modelPolicy(String owner) {
        return new ModelPolicyPO(
                "model-1", owner, "primary", "1.0.0", "DEEPSEEK", "deepseek-chat",
                BigDecimal.ZERO, BigDecimal.ONE, 32000, 4096, 3000, 60000, 1,
                "PUBLISHED", "b".repeat(64), "1", NOW, NOW);
    }
}
