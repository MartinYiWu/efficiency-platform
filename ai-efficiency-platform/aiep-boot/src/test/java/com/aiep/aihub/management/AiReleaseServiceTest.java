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
                .thenReturn(new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1", null));
        when(target.findModelPolicy("model-1")).thenReturn(new ModelPolicyPO(
                "model-1", "agent-1", "primary", "1.0.0", "DEEPSEEK", "deepseek-chat",
                new BigDecimal("0.1000"), new BigDecimal("0.9000"), 32000, 4096,
                5000, 120000, 1, "PUBLISHED", "c".repeat(64), "1", NOW, NOW));
        when(target.findRagPolicy("rag-1")).thenReturn(new RagPolicyPO(
                "rag-1", "agent-1", "default", "1.0.0", 3, 30, 30, 40, 12,
                12000, 12, "PUBLISHED", "d".repeat(64), "1", NOW, NOW,
                8, new BigDecimal("0.96"), 20, 3));
        var bindings = new java.util.ArrayList<PromptBindingPO>();
        bindings.add(new PromptBindingPO("version-1", "identity", 1, "prompt-1", "pv-1", true));
        for (String stage : List.of("equivalence", "conflict_screen", "evidence_extract")) {
            bindings.add(new PromptBindingPO("version-1", stage, 1, stage, stage + "-v1", true));
            when(target.findPromptDefinition(stage)).thenReturn(new PromptDefinitionPO(
                    stage, stage, "PRIVATE", "agent-1", stage, null, stage, "ACTIVE", "1", NOW, "1", NOW));
            when(target.findPromptVersion(stage + "-v1")).thenReturn(new PromptVersionPO(
                    stage + "-v1", stage, "1.0.0", "PUBLISHED", "a".repeat(64), "首版", "1", NOW, NOW));
            when(target.listPromptMessages(stage + "-v1")).thenReturn(List.of(
                    new PromptMessageTemplatePO(stage + "-system", stage + "-v1", 1, "SYSTEM", "instruction",
                            "仅判断原文", "TEXT", true, "b".repeat(64)),
                    new PromptMessageTemplatePO(stage + "-user", stage + "-v1", 2, "USER", "input",
                            "{{input_json}}", "JSON", false, "b".repeat(64))));
            when(target.listPromptVariables(stage + "-v1")).thenReturn(List.of());
        }
        when(target.listPromptBindings("version-1")).thenReturn(bindings);
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
        assertThat(requests.getAllValues().get(0).contractVersion()).isEqualTo("customer-service-release/2");

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

    @Test
    void rejectsMissingEvidenceStageBeforeDelivery() {
        when(repository.listPromptBindings("version-1")).thenReturn(List.of(
                new PromptBindingPO("version-1", "identity", 1, "prompt-1", "pv-1", true)));
        assertThatThrownBy(() -> service.publish("version-1", "dev"))
                .hasMessageContaining("阶段");
        verify(ai, never()).publishCustomerServiceRelease(anyString(), any());
    }

    @Test
    void rejectsLargeContextPolicyWithSameInputLimit() {
        when(repository.findPolicyBinding("version-1")).thenReturn(
                new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1", "model-1"));
        assertThatThrownBy(() -> service.publish("version-1", "dev"))
                .hasMessageContaining("输入上限");
        verify(ai, never()).publishCustomerServiceRelease(anyString(), any());
    }

    @Test
    void sharedGoldenSnapshotsKeepOriginalChecksumsIncludingNumericEdges() throws Exception {
        var mapper = new ObjectMapper();
        var checksum = AiReleaseService.class.getDeclaredMethod("checksum", CustomerServiceReleaseRequest.class);
        checksum.setAccessible(true);
        for (int version : List.of(1, 2)) {
            try (var stream = getClass().getResourceAsStream("/customer-service-release-v" + version + ".json")) {
                var request = mapper.readValue(stream, CustomerServiceReleaseRequest.class);
                assertThat(checksum.invoke(service, request)).isEqualTo(request.snapshotChecksum());
                var restored = mapper.readValue(mapper.writeValueAsBytes(request), CustomerServiceReleaseRequest.class);
                assertThat(checksum.invoke(service, restored)).isEqualTo(request.snapshotChecksum());
                if (version == 1) {
                    assertThat(mapper.valueToTree(restored).has("large_context_model_policy")).isFalse();
                    assertThat(mapper.valueToTree(restored).path("rag_policy").has("final_evidence_top_k")).isFalse();
                }
            }
        }
    }

    @Test
    void everyEvidenceFieldAndLargePolicyChangesSnapshotEvenWithSameDeclaredPolicyChecksum() throws Exception {
        var mapper = new ObjectMapper();
        var checksum = AiReleaseService.class.getDeclaredMethod("checksum", CustomerServiceReleaseRequest.class);
        checksum.setAccessible(true);
        var original = mapper.readTree(getClass().getResourceAsStream("/customer-service-release-v2.json"));
        for (String field : List.of("final_evidence_top_k", "similarity_candidate_threshold",
                "similarity_pair_limit", "adjacent_group_max_parents")) {
            var changed = original.deepCopy();
            ((com.fasterxml.jackson.databind.node.ObjectNode) changed.path("rag_policy")).put(field,
                    field.equals("similarity_candidate_threshold") ? new BigDecimal("0.95") : new BigDecimal("2"));
            var request = mapper.treeToValue(changed, CustomerServiceReleaseRequest.class);
            assertThat(checksum.invoke(service, request)).isNotEqualTo(original.path("snapshot_checksum").asText());
            assertThat(request.ragPolicy().checksum()).isEqualTo(original.path("rag_policy").path("checksum").asText());
        }
        var changed = (com.fasterxml.jackson.databind.node.ObjectNode) original.deepCopy();
        var large = (com.fasterxml.jackson.databind.node.ObjectNode) original.path("model_policy").deepCopy();
        large.put("max_input_tokens", 64000);
        changed.set("large_context_model_policy", large);
        var first = checksum.invoke(service, mapper.treeToValue(changed, CustomerServiceReleaseRequest.class));
        assertThat(first).isNotEqualTo(original.path("snapshot_checksum").asText());
        large.put("model_name", "other-large-model");
        assertThat(checksum.invoke(service, mapper.treeToValue(changed, CustomerServiceReleaseRequest.class))).isNotEqualTo(first);
    }

    @Test
    void rollbackResendsV1WithoutUpgradingOrRehashing() throws Exception {
        var mapper = new ObjectMapper();
        String json = new String(getClass().getResourceAsStream("/customer-service-release-v1.json").readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);
        var original = mapper.readValue(json, CustomerServiceReleaseRequest.class);
        when(repository.findRelease("old")).thenReturn(new com.aiep.aihub.repository.management.AiReleasePO(
                "old", "agent-1", "version-1", "dev", "ACTIVE", "snap", "1", NOW, null, NOW));
        when(repository.findReleaseSnapshot("old")).thenReturn(new com.aiep.aihub.repository.management.AiReleaseSnapshotPO(
                "snap", "old", json, original.snapshotChecksum(), "ACKNOWLEDGED", NOW, NOW));
        when(ai.publishCustomerServiceRelease(anyString(), any())).thenAnswer(invocation -> {
            CustomerServiceReleaseRequest request = invocation.getArgument(1);
            assertThat(request).isEqualTo(original);
            assertThat(mapper.readTree(mapper.writeValueAsString(request))).isEqualTo(mapper.readTree(json));
            return new CustomerServiceReleaseAck("customer-service-release-ack/1", invocation.getArgument(0),
                    request.snapshotChecksum(), "ACKNOWLEDGED");
        });
        service.rollback("old");
    }

    @Test
    void rejectsUnpublishedOrForeignLargePolicyAndInvalidPromptBeforeDelivery() {
        when(repository.findPolicyBinding("version-1")).thenReturn(
                new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1", "large"));
        for (String owner : List.of("agent-1", "foreign")) {
            when(repository.findModelPolicy("large")).thenReturn(new ModelPolicyPO(
                    "large", owner, "large", "1.0.0", "DEEPSEEK", "large", BigDecimal.ONE,
                    BigDecimal.ONE, 64000, 4096, 5000, 120000, 1,
                    owner.equals("agent-1") ? "DRAFT" : "PUBLISHED", "e".repeat(64), "1", NOW, NOW));
            assertThatThrownBy(() -> service.publish("version-1", "dev")).isInstanceOf(RuntimeException.class);
        }
        when(repository.findPolicyBinding("version-1")).thenReturn(
                new AgentVersionPolicyBindingPO("version-1", "model-1", "rag-1", null));
        when(repository.listPromptMessages("equivalence-v1")).thenReturn(List.of(
                new PromptMessageTemplatePO("bad", "equivalence-v1", 1, "SYSTEM", "bad",
                        "{{input_json}}", "TEXT", true, "b".repeat(64))));
        assertThatThrownBy(() -> service.publish("version-1", "dev")).hasMessageContaining("信任边界");
        verify(ai, never()).publishCustomerServiceRelease(anyString(), any());
    }

}
