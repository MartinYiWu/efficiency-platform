package com.aiep.aihub.evaluation;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationService;
import com.aiep.aihub.web.management.AiManagementExceptionHandler;
import com.aiep.aihub.web.management.RagEvaluationController;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class RagEvaluationControllerTest {
    @Test
    void exposesEvaluationDatasetsUnderAiHubManagementApi() throws Exception {
        RagEvaluationService service = mock(RagEvaluationService.class);
        when(service.listDatasets()).thenReturn(List.of(new Dataset(
                "dataset-1", "研发规范", "真实资料", "customer-service", "ACTIVE", 18,
                Instant.parse("2026-10-26T00:00:00Z"), Instant.parse("2026-10-26T01:00:00Z"))));
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new RagEvaluationController(service))
                .setControllerAdvice(new AiManagementExceptionHandler()).build();

        mvc.perform(get("/api/aihub/rag-evaluations/datasets"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data[0].id").value("dataset-1"))
                .andExpect(jsonPath("$.data[0].caseCount").value(18));
    }
}
