package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.evaluation.RagEvaluationService;
import com.aiep.aihub.application.evaluation.RagEvaluationService.CaseInput;
import com.aiep.aihub.repository.evaluation.RagEvaluationRepository;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.Executor;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RagEvaluationManagementServiceTest {
    @Test
    void importsCasesByStableCaseNumberAndReportsCreatedAndUpdatedCounts() {
        RagEvaluationRepository repository = mock(RagEvaluationRepository.class);
        when(repository.findDataset("dataset")).thenReturn(new Dataset(
                "dataset", "规范评测", null, "customer-service", "DRAFT", 1, Instant.now(), Instant.now()));
        when(repository.listCases("dataset")).thenReturn(List.of(caseValue("existing-id", "C-001", "旧问题")));
        when(repository.upsertCases(eq("dataset"), org.mockito.ArgumentMatchers.anyList())).thenReturn(2);
        Executor direct = Runnable::run;
        RagEvaluationService service = new RagEvaluationService(repository, mock(com.aiep.aihub.application.management.AiRagDebugService.class), direct);

        var result = service.importCases("dataset", List.of(
                input("C-001", "更新问题"), input("C-002", "新增问题")));

        assertThat(result.createdCount()).isEqualTo(1);
        assertThat(result.updatedCount()).isEqualTo(1);
        ArgumentCaptor<List<EvaluationCase>> values = ArgumentCaptor.forClass(List.class);
        verify(repository).upsertCases(eq("dataset"), values.capture());
        assertThat(values.getValue()).extracting(EvaluationCase::id)
                .first().isEqualTo("existing-id");
        assertThat(values.getValue()).extracting(EvaluationCase::question)
                .containsExactly("更新问题", "新增问题");
    }

    private static CaseInput input(String caseNo, String question) {
        return new CaseInput(caseNo, question, "COMPANY_KNOWLEDGE", List.of("事实"), List.of(),
                List.of("研发规范"), List.of(), 1, List.of("制度"), true);
    }

    private static EvaluationCase caseValue(String id, String caseNo, String question) {
        return new EvaluationCase(id, "dataset", caseNo, question, "COMPANY_KNOWLEDGE",
                List.of("事实"), List.of(), List.of("研发规范"), List.of(), 1, List.of("制度"), true);
    }
}
