package com.aiep.aihub.management;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.aihub.application.management.AiReleaseService;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionKnowledgeBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceReleaseAck;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;

class AiReleaseServiceTest {
    private static final LocalDateTime NOW = LocalDateTime.of(2026, 10, 20, 12, 0);
    private final AiManagementMappers repository = mock(AiManagementMappers.class);
    private final AiInvokeFacade ai = mock(AiInvokeFacade.class);
    private final AiReleaseService service = new AiReleaseService(repository, ai, new ObjectMapper());

    @BeforeEach
    void assets() {
        stubAssets(repository);
    }

    private void stubAssets(AiManagementMappers target) {
        when(target.findAgentVersion("version-1")).thenReturn(new AgentVersionPO(
                "version-1", "agent-1", "1.0.0", "customer-service", "1",
                "VALIDATED", "首版", "1", NOW, null));
        when(target.findAgent("agent-1")).thenReturn(new AgentDefinitionPO(
                "agent-1", "customer-service", "智能客服", null, "CUSTOMER_SERVICE",
                "ACTIVE", "1", NOW, "1", NOW));
        when(target.findPolicyBinding("version-1"))
                .thenReturn(new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1"));
        when(target.findModelPolicy("model-1")).thenReturn(new ModelPolicyPO(
                "model-1", "agent-1", "primary", "1.0.0", "DEEPSEEK", "deepseek-chat",
                new BigDecimal("0.1000"), new BigDecimal("0.9000"), 32000, 4096,
                5000, 120000, 1, "PUBLISHED", "c".repeat(64), "1", NOW, NOW));
        when(target.findRagPolicy("rag-1")).thenReturn(new RagPolicyPO(
                "rag-1", "agent-1", "default", "1.0.0", 3, 30, 30, 40, 12,
                12000, 12, "PUBLISHED", "d".repeat(64), "1", NOW, NOW));
        when(target.listPromptBindings("version-1")).thenReturn(List.of(
                new PromptBindingPO("version-1", "identity", 1, "prompt-1", "pv-1", true)));
        when(target.findPromptDefinition("prompt-1")).thenReturn(new PromptDefinitionPO(
                "prompt-1", "customer_service.identity.system", "PRIVATE", "agent-1",
                "身份", null, "identity", "ACTIVE", "1", NOW, "1", NOW));
        when(target.findPromptVersion("pv-1")).thenReturn(new PromptVersionPO(
                "pv-1", "prompt-1", "1.0.0", "PUBLISHED", "a".repeat(64),
                "首版", "1", NOW, NOW));
        when(target.listPromptMessages("pv-1")).thenReturn(List.of(
                new PromptMessageTemplatePO("message-1", "pv-1", 1, "SYSTEM", "identity",
                        "你是内部智能客服", "TEXT", true, "b".repeat(64))));
        when(target.listPromptVariables("pv-1")).thenReturn(List.of());
        when(target.listKnowledgeBindings("version-1")).thenReturn(List.of(
                new AgentVersionKnowledgeBindingPO("version-1", "22222222-2222-2222-2222-222222222222",
                        "33333333-3333-3333-3333-333333333333", 1, true)));
        when(target.isIndexReleaseReady(anyString())).thenReturn(true);
    }

    @Test
    void activatesOnlyAfterMatchingAgentAcknowledgement() {
        when(ai.publishCustomerServiceRelease(anyString(), any()))
                .thenAnswer(invocation -> {
                    CustomerServiceReleaseRequest request = invocation.getArgument(1);
                    return new CustomerServiceReleaseAck(
                            "customer-service-release-ack/1", invocation.getArgument(0),
                            request.snapshotChecksum(), "ACKNOWLEDGED");
                });

        var release = service.publish("version-1", "dev");

        InOrder order = inOrder(repository, ai);
        order.verify(repository).insertRelease(any(), any());
        order.verify(ai).publishCustomerServiceRelease(eq(release.id()), any());
        order.verify(repository).acknowledgeAndActivateRelease(
                release.id(), release.releaseSnapshotId(), "agent-1", "dev", "version-1");
    }

    @Test
    void canonicalSnapshotIsStableAndRemoteFailurePreservesActiveRelease() {
        when(ai.publishCustomerServiceRelease(anyString(), any()))
                .thenAnswer(invocation -> {
                    CustomerServiceReleaseRequest request = invocation.getArgument(1);
                    return new CustomerServiceReleaseAck(
                            "customer-service-release-ack/1", invocation.getArgument(0),
                            request.snapshotChecksum(), "ACKNOWLEDGED");
                });
        ArgumentCaptor<CustomerServiceReleaseRequest> requests =
                ArgumentCaptor.forClass(CustomerServiceReleaseRequest.class);
        service.publish("version-1", "dev");
        service.publish("version-1", "dev");
        verify(ai, org.mockito.Mockito.times(2))
                .publishCustomerServiceRelease(anyString(), requests.capture());
        assertThat(requests.getAllValues().get(0).snapshotChecksum())
                .isEqualTo(requests.getAllValues().get(1).snapshotChecksum());
        assertThat(requests.getAllValues().get(0).snapshotChecksum())
                .isEqualTo("3dcd68316ff91d55b82aa3ecfd61972b45813e056f7809d6b0f4a4b65e71984b");

        AiManagementMappers failedRepository = mock(AiManagementMappers.class);
        AiInvokeFacade failedAi = mock(AiInvokeFacade.class);
        AiReleaseService failed = new AiReleaseService(failedRepository, failedAi, new ObjectMapper());
        stubAssets(failedRepository);
        when(failedAi.publishCustomerServiceRelease(anyString(), any()))
                .thenThrow(new RuntimeException("provider unavailable"));
        assertThatThrownBy(() -> failed.publish("version-1", "dev"))
                .isInstanceOf(RuntimeException.class);
        verify(failedRepository, never()).acknowledgeAndActivateRelease(
                anyString(), anyString(), anyString(), anyString(), anyString());
    }

}
