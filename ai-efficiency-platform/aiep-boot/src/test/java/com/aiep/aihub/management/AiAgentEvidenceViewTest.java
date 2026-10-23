package com.aiep.aihub.management;

import com.aiep.aihub.application.management.AiAgentManagementService;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class AiAgentEvidenceViewTest {
    @Test
    void exposesReadOnlyEvidenceBindingsInExistingDetail() {
        var repository = mock(AiManagementMappers.class);
        when(repository.findAgent("a")).thenReturn(new AgentDefinitionPO(
                "a","customer-service","客服",null,"CUSTOMER_SERVICE","ACTIVE","1",null,"1",null));
        var result = new ObjectMapper().valueToTree(new AiAgentManagementService(repository).get("a"));
        assertThat(result.path("evidenceBindings").isArray()).isTrue();
    }
}
