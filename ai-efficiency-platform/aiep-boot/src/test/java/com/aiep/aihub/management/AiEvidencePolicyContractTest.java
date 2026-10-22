package com.aiep.aihub.management;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import com.aiep.aihub.application.management.AiPolicyManagementService;
import com.aiep.aihub.application.management.AiPolicyManagementService.RagPolicyInput;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class AiEvidencePolicyContractTest {
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
    private static final String BASE = """
        {"ownerAgentId":"agent-1","policyKey":"rag","semanticVersion":"2.0.0",
         "rewriteQueryLimit":3,"vectorTopK":30,"ftsTopK":30,"fusionTopK":40,
         "rerankTopK":12,"contextTokenLimit":12000,"citationLimit":12,"checksum":"abc"}
        """;

    @Test
    void newPolicyDefaultsAreFrozenInSavedRecord() throws Exception {
        var input = mapper.readValue(BASE, RagPolicyInput.class);
        var service = new AiPolicyManagementService(mock(AiManagementMappers.class));
        var value = mapper.valueToTree(service.saveRag(input));
        assertThat(value.path("finalEvidenceTopK").asInt()).isEqualTo(8);
        assertThat(value.path("similarityCandidateThreshold").decimalValue()).isEqualByComparingTo("0.96");
        assertThat(value.path("similarityPairLimit").asInt()).isEqualTo(20);
        assertThat(value.path("adjacentGroupMaxParents").asInt()).isEqualTo(3);
    }

    @Test
    void policyRangeChecksRejectEveryOutsideBoundary() throws Exception {
        for (String field : new String[]{"finalEvidenceTopK", "similarityCandidateThreshold",
                "similarityPairLimit", "adjacentGroupMaxParents"}) {
            var value = (com.fasterxml.jackson.databind.node.ObjectNode) mapper.readTree(BASE);
            value.put(field, 0);
            assertThatThrownBy(() -> mapper.treeToValue(value, RagPolicyInput.class))
                    .hasMessageContaining("范围");
        }
    }

    @Test
    void persistenceWritesAllEvidencePolicyColumns() throws Exception {
        var input = mapper.readValue(BASE, RagPolicyInput.class);
        var value = new AiPolicyManagementService(mock(AiManagementMappers.class)).saveRag(input);
        var jdbc = mock(org.springframework.jdbc.core.JdbcTemplate.class);
        var repository = new com.aiep.aihub.repository.management.JdbcAiManagementMappers(jdbc);
        repository.insertRagPolicy(value);
        repository.updateRagPolicy(value);
        var invocations = org.mockito.Mockito.mockingDetails(jdbc).getInvocations();
        assertThat(invocations).hasSize(2);
        assertThat(invocations.stream().filter(invocation -> ((String) invocation.getArgument(0)).startsWith("INSERT ")).count()).isEqualTo(1);
        assertThat(invocations.stream().filter(invocation -> ((String) invocation.getArgument(0)).startsWith("UPDATE ")).count()).isEqualTo(1);
        for (var invocation : invocations) {
            assertThat((String) invocation.getArgument(0)).contains("final_evidence_top_k",
                    "similarity_candidate_threshold", "similarity_pair_limit", "adjacent_group_max_parents");
        }
    }

    @Test
    void optionalLargeContextBindingCanBeSetAndRemoved() {
        var repository = mock(AiManagementMappers.class);
        org.mockito.Mockito.when(repository.findAgentVersion("v")).thenReturn(
                new com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO(
                        "v", "agent", "2", "customer-service", "2", "DRAFT", "test", "1", null, null));
        org.mockito.Mockito.when(repository.findPolicyBinding("v")).thenReturn(
                new com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO("v", "primary", "rag", null));
        for (String key : new String[]{"primary", "large"}) {
            org.mockito.Mockito.when(repository.findModelPolicy(key)).thenReturn(
                    new com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO(
                        key, "agent", key, "1", "DEEPSEEK", key, java.math.BigDecimal.ONE,
                        java.math.BigDecimal.ONE, key.equals("primary") ? 32000 : 64000,
                        4096, 5000, 120000, 1, "PUBLISHED", "checksum", "1", null, null));
        }
        var service = new com.aiep.aihub.application.management.AiAgentManagementService(repository);
        service.bindLargeContextModelPolicy("v", "large");
        service.bindLargeContextModelPolicy("v", null);
        org.mockito.Mockito.verify(repository).upsertLargeContextModelPolicyBinding("v", "large");
        org.mockito.Mockito.verify(repository).upsertLargeContextModelPolicyBinding("v", null);
        assertThatThrownBy(() -> service.bindLargeContextModelPolicy("v", "primary")).hasMessageContaining("输入上限");
    }

    @Test
    void legacyPublishedPolicyCanStillBeRetiredWithoutAddingDefaults() {
        var repository = mock(AiManagementMappers.class);
        org.mockito.Mockito.when(repository.findRagPolicy("old")).thenReturn(
                new com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO(
                        "old", "agent", "rag", "1.0.0", 3, 30, 30, 40, 12, 12000, 12,
                        "PUBLISHED", "old-digest", "1", null, null, null, null, null, null));
        var retired = new AiPolicyManagementService(repository).transitionRag("old", "RETIRED");
        assertThat(retired.status()).isEqualTo("RETIRED");
        assertThat(retired.finalEvidenceTopK()).isNull();
        assertThat(retired.checksum()).isEqualTo("old-digest");
    }

    @Test
    void changingPrimaryCannotInvalidateBoundLargeModel() {
        var repository = mock(AiManagementMappers.class);
        org.mockito.Mockito.when(repository.findAgentVersion("v")).thenReturn(
                new com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO(
                        "v", "agent", "2", "customer-service", "2", "DRAFT", "test", "1", null, null));
        org.mockito.Mockito.when(repository.findPolicyBinding("v")).thenReturn(
                new com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO("v", "old", "rag", "large"));
        var policy = new com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO(
                "large", "agent", "model", "1", "DEEPSEEK", "model", java.math.BigDecimal.ONE,
                java.math.BigDecimal.ONE, 64000, 4096, 5000, 120000, 1, "PUBLISHED", "checksum", "1", null, null);
        org.mockito.Mockito.when(repository.findModelPolicy("large")).thenReturn(policy);
        org.mockito.Mockito.when(repository.findModelPolicy("new")).thenReturn(policy);
        var service = new com.aiep.aihub.application.management.AiAgentManagementService(repository);
        assertThatThrownBy(() -> service.bindModelPolicy("v", "new")).hasMessageContaining("输入上限");
        org.mockito.Mockito.verify(repository, org.mockito.Mockito.never()).upsertModelPolicyBinding("v", "new");
    }
}
