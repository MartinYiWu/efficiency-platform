package com.aiep.aihub.application.evaluation;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationRun;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.KnowledgeBinding;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.management.AiRagDebugService;
import com.aiep.aihub.application.management.AiManagementException;
import com.aiep.aihub.repository.evaluation.RagEvaluationRepository;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.aiep.platformai.agent.AgentTransportException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.UUID;
import java.util.concurrent.Executor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class RagEvaluationService {
    private static final Logger log = LoggerFactory.getLogger(RagEvaluationService.class);
    private final RagEvaluationRepository repository;
    private final AiRagDebugService ragDebug;
    private final Executor executor;
    public RagEvaluationService(RagEvaluationRepository repository, AiRagDebugService ragDebug,
                                @Qualifier("ragEvaluationExecutor") Executor ragEvaluationExecutor) {
        this.repository = repository;
        this.ragDebug = ragDebug;
        this.executor = ragEvaluationExecutor;
    }

    public Dataset createDataset(CreateDatasetRequest request) {
        requireText(request.name(), "AI_RAG_EVAL_DATASET_NAME_REQUIRED");
        requireText(request.agentKey(), "AI_RAG_EVAL_AGENT_REQUIRED");
        String status = request.status() == null || request.status().isBlank() ? "DRAFT" : request.status();
        if (!List.of("DRAFT", "ACTIVE", "ARCHIVED").contains(status)) {
            throw new AiManagementException("AI_RAG_EVAL_DATASET_STATUS_INVALID", "评测数据集状态无效");
        }
        Instant now = Instant.now();
        return repository.createDataset(new Dataset(UUID.randomUUID().toString(), request.name().trim(),
                trimToNull(request.description()), request.agentKey().trim(), status, 0, now, now));
    }

    public List<Dataset> listDatasets() {
        return repository.listDatasets();
    }

    public DatasetDetail getDataset(String datasetId) {
        Dataset dataset = requireDataset(datasetId);
        return new DatasetDetail(dataset, repository.listCases(datasetId), repository.listRuns(datasetId));
    }

    public ImportResult importCases(String datasetId, List<CaseInput> inputs) {
        requireDataset(datasetId);
        if (inputs == null || inputs.isEmpty()) {
            throw new AiManagementException("AI_RAG_EVAL_CASE_EMPTY", "评测用例不能为空");
        }
        Map<String, EvaluationCase> existing = new LinkedHashMap<>();
        repository.listCases(datasetId).forEach(value -> existing.put(value.caseNo(), value));
        Set<String> importedCaseNumbers = new HashSet<>();
        List<EvaluationCase> values = new ArrayList<>();
        int created = 0;
        int updated = 0;
        for (CaseInput input : inputs) {
            validateCase(input);
            if (!importedCaseNumbers.add(input.caseNo().trim())) {
                throw new AiManagementException("AI_RAG_EVAL_CASE_NO_DUPLICATED", "批量导入中存在重复用例编号");
            }
            EvaluationCase current = existing.get(input.caseNo());
            String id = current == null ? UUID.randomUUID().toString() : current.id();
            if (current == null) created++; else updated++;
            values.add(toCase(id, datasetId, input));
        }
        repository.upsertCases(datasetId, values);
        return new ImportResult(created, updated, values.size());
    }

    public EvaluationCase createCase(String datasetId, CaseInput input) {
        if (repository.listCases(datasetId).stream().anyMatch(value -> value.caseNo().equals(input.caseNo()))) {
            throw new AiManagementException("AI_RAG_EVAL_CASE_NO_CONFLICT", "用例编号已存在");
        }
        importCases(datasetId, List.of(input));
        return repository.listCases(datasetId).stream().filter(value -> value.caseNo().equals(input.caseNo()))
                .findFirst().orElseThrow();
    }

    public EvaluationCase updateCase(String datasetId, String caseId, CaseInput input) {
        requireDataset(datasetId);
        validateCase(input);
        EvaluationCase current = repository.listCases(datasetId).stream().filter(value -> value.id().equals(caseId))
                .findFirst().orElseThrow(() -> new AiManagementException("AI_RAG_EVAL_CASE_NOT_FOUND", "评测用例不存在"));
        if (!current.caseNo().equals(input.caseNo().trim())) {
            throw new AiManagementException("AI_RAG_EVAL_CASE_NO_IMMUTABLE", "稳定用例编号不允许修改");
        }
        boolean caseNoConflict = repository.listCases(datasetId).stream()
                .anyMatch(value -> !value.id().equals(caseId) && value.caseNo().equals(input.caseNo()));
        if (caseNoConflict) throw new AiManagementException("AI_RAG_EVAL_CASE_NO_CONFLICT", "用例编号已存在");
        EvaluationCase value = toCase(current.id(), datasetId, input);
        repository.upsertCases(datasetId, List.of(value));
        return value;
    }

    public List<EvaluationRun> listRuns(String datasetId) {
        requireDataset(datasetId);
        return repository.listRuns(datasetId);
    }

    public RunDetail getRun(String runId) {
        EvaluationRun run = requireRun(runId);
        return new RunDetail(run, repository.listCases(run.datasetId()), repository.listResults(runId));
    }

    public RunComparison compareRuns(String baselineRunId, String candidateRunId) {
        EvaluationRun baseline = requireRun(baselineRunId);
        EvaluationRun candidate = requireRun(candidateRunId);
        if (!baseline.datasetId().equals(candidate.datasetId())) {
            throw new AiManagementException("AI_RAG_EVAL_RUN_DATASET_MISMATCH", "只能比较同一数据集的评测批次");
        }
        Map<String, CaseResult> baselineResults = byCase(repository.listResults(baselineRunId));
        Map<String, CaseResult> candidateResults = byCase(repository.listResults(candidateRunId));
        List<CaseChange> changes = candidateResults.values().stream().map(current -> {
            CaseResult previous = baselineResults.get(current.caseId());
            String change = previous == null ? "NEW" : previous.passed() == current.passed()
                    ? "UNCHANGED" : current.passed() ? "IMPROVED" : "REGRESSED";
            return new CaseChange(current.caseId(), previous == null ? null : previous.passed(), current.passed(), change);
        }).toList();
        return new RunComparison(baseline, candidate, metricDeltas(baseline.metrics(), candidate.metrics()), changes);
    }

    public EvaluationRun startRun(StartRunRequest request) {
        requireDataset(request.datasetId());
        requireText(request.agentKey(), "AI_RAG_EVAL_AGENT_REQUIRED");
        requireText(request.agentVersionId(), "AI_RAG_EVAL_AGENT_VERSION_REQUIRED");
        requireText(request.ragPolicyVersionId(), "AI_RAG_EVAL_RAG_POLICY_REQUIRED");
        if (request.knowledgeBindings().isEmpty()) {
            throw new AiManagementException("AI_RAG_EVAL_KNOWLEDGE_BINDING_REQUIRED", "评测知识绑定不能为空");
        }
        var cases = repository.listEnabledCases(request.datasetId());
        if (cases.isEmpty()) throw new AiManagementException("AI_RAG_EVAL_CASE_EMPTY", "没有启用的评测用例");
        Instant now = Instant.now();
        EvaluationRun run = repository.createRun(new EvaluationRun(
                UUID.randomUUID().toString(), request.datasetId(), request.agentKey(), request.agentVersionId(),
                request.ragPolicyVersionId(), request.knowledgeBindings(), "PENDING", cases.size(), 0, 0,
                null, null, null, now, null, null));
        executor.execute(() -> execute(run, cases));
        return run;
    }

    private void execute(EvaluationRun run, List<RagEvaluationModels.EvaluationCase> cases) {
        Instant startedAt = Instant.now();
        repository.markRunning(run.id(), startedAt);
        List<RagEvaluationMetrics.CaseMetrics> quality = new ArrayList<>();
        List<Long> latencies = new ArrayList<>();
        int executionFailures = 0;
        for (var testCase : cases) {
            long started = System.nanoTime();
            try {
                CustomerServiceDebugView response = ragDebug.execute(new AiRagDebugService.Request(
                        run.agentKey(), testCase.question(), run.agentVersionId(), run.ragPolicyVersionId(),
                        run.knowledgeBindings().stream().map(item -> new AiRagDebugService.KnowledgeBinding(
                                item.knowledgeBaseId(), item.indexReleaseId())).toList()));
                long latency = elapsedMs(started);
                Set<String> allowedIndexes = run.knowledgeBindings().stream()
                        .map(KnowledgeBinding::indexReleaseId).collect(java.util.stream.Collectors.toSet());
                var metrics = RagEvaluationMetrics.evaluate(testCase, response, allowedIndexes);
                quality.add(metrics);
                latencies.add(latency);
                repository.saveResult(new CaseResult(UUID.randomUUID().toString(), run.id(), testCase.id(),
                        response.debugRunId(), "SUCCEEDED", metrics.passed(), latency, response.answerMode(),
                        response.answerMarkdown(), response.citations() == null ? List.of() : response.citations(),
                        metrics, null, null, Instant.now()));
                log.info("event=rag_evaluation_case_completed eval_run_id={} case_id={} debug_run_id={} latency_ms={} passed={}",
                        run.id(), testCase.id(), response.debugRunId(), latency, metrics.passed());
            } catch (Exception error) {
                executionFailures++;
                long latency = elapsedMs(started);
                latencies.add(latency);
                String code = errorCode(error);
                repository.saveResult(new CaseResult(UUID.randomUUID().toString(), run.id(), testCase.id(),
                        null, "FAILED", false, latency, null, null, List.of(), null,
                        code, "评测调用失败", Instant.now()));
                log.error("event=rag_evaluation_case_failed eval_run_id={} case_id={} latency_ms={} error_code={} error_type={}",
                        run.id(), testCase.id(), latency, code, error.getClass().getSimpleName());
            }
        }
        int passed = (int) quality.stream().filter(RagEvaluationMetrics.CaseMetrics::passed).count();
        String status = executionFailures == cases.size() ? "FAILED" : executionFailures > 0 ? "PARTIAL_FAILED" : "SUCCEEDED";
        repository.completeRun(new EvaluationRun(run.id(), run.datasetId(), run.agentKey(), run.agentVersionId(),
                run.ragPolicyVersionId(), run.knowledgeBindings(), status, cases.size(), passed,
                cases.size() - passed, RagEvaluationMetrics.summarize(cases.size(), quality, latencies), null, null,
                run.createdAt(), startedAt, Instant.now()));
    }

    private static long elapsedMs(long started) {
        return Math.max(0, (System.nanoTime() - started) / 1_000_000);
    }

    private static String errorCode(Exception error) {
        if (error instanceof AgentTransportException transport) return transport.getErrorCode();
        if (error instanceof AiManagementException management) return management.getCode();
        return error.getMessage() == null || error.getMessage().isBlank()
                ? error.getClass().getSimpleName() : error.getMessage();
    }

    private Dataset requireDataset(String id) {
        Dataset dataset = repository.findDataset(id);
        if (dataset == null) throw new AiManagementException("AI_RAG_EVAL_DATASET_NOT_FOUND", "评测数据集不存在");
        return dataset;
    }

    private EvaluationRun requireRun(String id) {
        EvaluationRun run = repository.findRun(id);
        if (run == null) throw new AiManagementException("AI_RAG_EVAL_RUN_NOT_FOUND", "评测批次不存在");
        return run;
    }

    private static void validateCase(CaseInput input) {
        if (input == null) throw new AiManagementException("AI_RAG_EVAL_CASE_INVALID", "评测用例不能为空");
        requireText(input.caseNo(), "AI_RAG_EVAL_CASE_NO_REQUIRED");
        requireText(input.question(), "AI_RAG_EVAL_QUESTION_REQUIRED");
        if (!List.of("COMPANY_KNOWLEDGE", "MIXED", "GENERAL_ADVICE", "INSUFFICIENT_EVIDENCE")
                .contains(input.expectedAnswerMode())) {
            throw new AiManagementException("AI_RAG_EVAL_ANSWER_MODE_INVALID", "预期回答模式无效");
        }
        if (input.minCitationCount() < 0) {
            throw new AiManagementException("AI_RAG_EVAL_CITATION_COUNT_INVALID", "最少引用数不能小于零");
        }
    }

    private static EvaluationCase toCase(String id, String datasetId, CaseInput input) {
        return new EvaluationCase(id, datasetId, input.caseNo().trim(), input.question().trim(),
                input.expectedAnswerMode(), safeList(input.expectedFacts()), safeList(input.prohibitedFacts()),
                safeList(input.expectedDocumentTitles()), safeList(input.expectedDocumentVersionIds()),
                input.minCitationCount(), safeList(input.tags()), input.enabled());
    }

    private static List<String> safeList(List<String> values) {
        return values == null ? List.of() : values.stream().map(String::trim).filter(value -> !value.isEmpty()).toList();
    }

    private static void requireText(String value, String code) {
        if (value == null || value.isBlank()) throw new AiManagementException(code, "评测请求缺少必填字段");
    }

    private static String trimToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static Map<String, CaseResult> byCase(List<CaseResult> values) {
        Map<String, CaseResult> result = new LinkedHashMap<>();
        values.forEach(value -> result.put(value.caseId(), value));
        return result;
    }

    private static Map<String, Double> metricDeltas(RagEvaluationMetrics.Summary baseline,
                                                      RagEvaluationMetrics.Summary candidate) {
        if (baseline == null || candidate == null) return Map.of();
        Map<String, Double> values = new LinkedHashMap<>();
        addDelta(values, "executionSuccessRate", baseline.executionSuccessRate(), candidate.executionSuccessRate());
        addDelta(values, "answerModeAccuracy", baseline.answerModeAccuracy(), candidate.answerModeAccuracy());
        addDelta(values, "expectedFactRecall", baseline.expectedFactRecall(), candidate.expectedFactRecall());
        addDelta(values, "prohibitedFactRate", baseline.prohibitedFactRate(), candidate.prohibitedFactRate());
        addDelta(values, "sourceRecallAtK", baseline.sourceRecallAtK(), candidate.sourceRecallAtK());
        addDelta(values, "citationComplianceRate", baseline.citationComplianceRate(), candidate.citationComplianceRate());
        addDelta(values, "versionAccuracy", baseline.versionAccuracy(), candidate.versionAccuracy());
        addDelta(values, "casePassRate", baseline.casePassRate(), candidate.casePassRate());
        addDelta(values, "latencyP50Ms", (double) baseline.latencyP50Ms(), (double) candidate.latencyP50Ms());
        addDelta(values, "latencyP95Ms", (double) baseline.latencyP95Ms(), (double) candidate.latencyP95Ms());
        return Map.copyOf(values);
    }

    private static void addDelta(Map<String, Double> values, String key, Double baseline, Double candidate) {
        if (baseline != null && candidate != null) values.put(key, candidate - baseline);
    }

    public record StartRunRequest(String datasetId, String agentKey, String agentVersionId,
                                  String ragPolicyVersionId, List<KnowledgeBinding> knowledgeBindings) {
        public StartRunRequest {
            knowledgeBindings = List.copyOf(knowledgeBindings);
        }
    }

    public record CreateDatasetRequest(String name, String description, String agentKey, String status) { }
    public record CaseInput(String caseNo, String question, String expectedAnswerMode, List<String> expectedFacts,
                            List<String> prohibitedFacts, List<String> expectedDocumentTitles,
                            List<String> expectedDocumentVersionIds, int minCitationCount, List<String> tags,
                            boolean enabled) { }
    public record ImportResult(int createdCount, int updatedCount, int totalCount) { }
    public record DatasetDetail(Dataset dataset, List<EvaluationCase> cases, List<EvaluationRun> runs) { }
    public record RunDetail(EvaluationRun run, List<EvaluationCase> cases, List<CaseResult> results) { }
    public record CaseChange(String caseId, Boolean baselinePassed, boolean candidatePassed, String change) { }
    public record RunComparison(EvaluationRun baseline, EvaluationRun candidate, Map<String, Double> metricDeltas,
                                List<CaseChange> caseChanges) { }
}
