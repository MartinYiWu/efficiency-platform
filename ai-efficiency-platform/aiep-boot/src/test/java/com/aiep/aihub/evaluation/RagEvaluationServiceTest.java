package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationRun;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.KnowledgeBinding;
import com.aiep.aihub.application.evaluation.RagEvaluationService;
import com.aiep.aihub.application.management.AiRagDebugService;
import com.aiep.aihub.repository.evaluation.RagEvaluationRepository;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executor;
import org.junit.jupiter.api.Test;

class RagEvaluationServiceTest {

    @Test
    void executesEveryCasePersistsFailuresAndCompletesPartialBatch() throws Exception {
        InMemoryRepository repository = new InMemoryRepository();
        repository.dataset = new Dataset("dataset", "规范评测", null, "customer-service", "ACTIVE", 2,
                Instant.parse("2026-10-26T00:00:00Z"), Instant.parse("2026-10-26T00:00:00Z"));
        repository.cases = List.of(
                new EvaluationCase("c1", "dataset", "AI-001", "是否允许MAX？", "COMPANY_KNOWLEDGE",
                        List.of("禁止开启MAX"), List.of(), List.of("研发内部AI使用规范"), List.of(), 1, List.of(), true),
                new EvaluationCase("c2", "dataset", "AI-002", "额度多少？", "COMPANY_KNOWLEDGE",
                        List.of("100美元"), List.of(), List.of("研发内部AI使用规范"), List.of(), 1, List.of(), true));
        AiRagDebugService debug = mock(AiRagDebugService.class);
        when(debug.execute(any())).thenReturn(response()).thenThrow(new IllegalStateException("MODEL_TIMEOUT"));
        Executor direct = Runnable::run;
        RagEvaluationService service = new RagEvaluationService(repository, debug, direct);

        EvaluationRun created = service.startRun(new RagEvaluationService.StartRunRequest(
                "dataset", "customer-service", "agent-version", "rag-version",
                List.of(new KnowledgeBinding("kb", "index"))));

        EvaluationRun finished = repository.findRun(created.id());
        assertThat(finished.status()).isEqualTo("PARTIAL_FAILED");
        assertThat(finished.totalCount()).isEqualTo(2);
        assertThat(finished.passedCount()).isEqualTo(1);
        assertThat(finished.failedCount()).isEqualTo(1);
        assertThat(repository.results).hasSize(2);
        assertThat(repository.results.get(0).debugRunId()).isEqualTo("debug-1");
        assertThat(repository.results.get(1).errorCode()).isEqualTo("MODEL_TIMEOUT");
    }

    private CustomerServiceDebugView response() throws Exception {
        return new ObjectMapper().readValue("""
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"debug-1",
                 "status":"SUCCEEDED","stages":[],"answer_mode":"COMPANY_KNOWLEDGE",
                 "answer_markdown":"禁止开启MAX。[1]","citations":[{"citation_no":1,
                 "knowledge_base_id":"kb","document_id":"doc","document_version_id":"version",
                 "index_release_id":"index","chunk_id":"chunk","document_title":"研发内部AI使用规范",
                 "version_no":1,"section_path":"模型","page_no":1,"quoted_text":"禁止开启MAX",
                 "content_hash":"hash","parent_id":"parent","citation_type":"FULL_PARENT",
                 "original_spans":[{"start_offset":0,"end_offset":7,"content_hash":"span"}]}],
                 "error_code":null,"error_message":null}
                """, CustomerServiceDebugView.class);
    }

    private static final class InMemoryRepository implements RagEvaluationRepository {
        Dataset dataset;
        List<EvaluationCase> cases = List.of();
        EvaluationRun run;
        final List<com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult> results = new ArrayList<>();

        @Override public Dataset createDataset(Dataset value) { dataset = value; return value; }
        @Override public List<Dataset> listDatasets() { return dataset == null ? List.of() : List.of(dataset); }
        @Override public Dataset findDataset(String id) { return dataset != null && dataset.id().equals(id) ? dataset : null; }
        @Override public int upsertCases(String datasetId, List<EvaluationCase> values) { cases = values; return values.size(); }
        @Override public List<EvaluationCase> listCases(String datasetId) { return cases; }
        @Override public List<EvaluationCase> listEnabledCases(String datasetId) { return cases; }
        @Override public EvaluationRun createRun(EvaluationRun value) { run = value; return value; }
        @Override public void markRunning(String id, Instant startedAt) { run = run.withStatus("RUNNING", startedAt, null); }
        @Override public void saveResult(com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult value) { results.add(value); }
        @Override public void completeRun(EvaluationRun value) { run = value; }
        @Override public EvaluationRun findRun(String id) { return run; }
        @Override public List<EvaluationRun> listRuns(String datasetId) { return run == null ? List.of() : List.of(run); }
        @Override public List<com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult> listResults(String runId) { return results; }
    }
}
