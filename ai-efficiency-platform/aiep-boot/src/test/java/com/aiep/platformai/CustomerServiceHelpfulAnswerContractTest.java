package com.aiep.platformai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CustomerServiceHelpfulAnswerContractTest {
    private final ObjectMapper json = new ObjectMapper().enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    private static final String ORIGINAL = """
            {"sufficient":false,"supported_claims":[],"unsupported_claims":["报销流程"],
             "conflicts":[],"recommended_mode":"GENERAL_ADVICE"}
            """;

    @Test void acceptsHelpfulDecisionWithoutDiscardingNewFacts() throws Exception {
        var node = json.readTree(ORIGINAL);
        ((com.fasterxml.jackson.databind.node.ObjectNode) node).put("evidence_status", "NO_RELEVANT_EVIDENCE")
                .put("general_advice_allowed", true).putArray("general_advice_scope").add("一般票据整理方法");
        ((com.fasterxml.jackson.databind.node.ObjectNode) node).putArray("company_specific_unknowns").add("公司审批节点");
        var result = json.treeToValue(node, CustomerServiceDebugView.Sufficiency.class);
        assertThat(result.evidenceStatus()).isEqualTo("NO_RELEVANT_EVIDENCE");
        assertThat(result.generalAdviceAllowed()).isTrue();
        assertThat(result.generalAdviceScope()).containsExactly("一般票据整理方法");
        assertThat(result.companySpecificUnknowns()).containsExactly("公司审批节点");
    }

    @Test void preservesOldDecisionAndUnknownFieldGuard() throws Exception {
        assertThat(json.readValue(ORIGINAL, CustomerServiceDebugView.Sufficiency.class).generalAdviceAllowed()).isNull();
        var node = (com.fasterxml.jackson.databind.node.ObjectNode) json.readTree(ORIGINAL);
        node.put("unregistered_decision", true);
        assertThatThrownBy(() -> json.treeToValue(node, CustomerServiceDebugView.Sufficiency.class))
                .isInstanceOf(com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException.class);
    }
}
