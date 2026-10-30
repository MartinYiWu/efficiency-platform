package com.aiep.aihub.application.evaluation;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.time.Instant;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;

public final class RagEvaluationModels {
    private RagEvaluationModels() { }

    public record EvaluationCase(
            String id,
            String datasetId,
            String caseNo,
            String question,
            String expectedAnswerMode,
            List<String> expectedFacts,
            List<String> prohibitedFacts,
            List<String> expectedDocumentTitles,
            List<String> expectedDocumentVersionIds,
            int minCitationCount,
            List<String> tags,
            boolean enabled,
            Map<String, List<String>> expectedFactAlternatives) {
        public EvaluationCase(String id, String datasetId, String caseNo, String question,
                              String expectedAnswerMode, List<String> expectedFacts, List<String> prohibitedFacts,
                              List<String> expectedDocumentTitles, List<String> expectedDocumentVersionIds,
                              int minCitationCount, List<String> tags, boolean enabled) {
            this(id, datasetId, caseNo, question, expectedAnswerMode, expectedFacts, prohibitedFacts,
                    expectedDocumentTitles, expectedDocumentVersionIds, minCitationCount, tags, enabled, Map.of());
        }

        public EvaluationCase {
            expectedFacts = List.copyOf(expectedFacts);
            prohibitedFacts = List.copyOf(prohibitedFacts);
            expectedDocumentTitles = List.copyOf(expectedDocumentTitles);
            expectedDocumentVersionIds = List.copyOf(expectedDocumentVersionIds);
            tags = List.copyOf(tags);
            expectedFactAlternatives = expectedFactAlternatives == null ? Map.of()
                    : expectedFactAlternatives.entrySet().stream().collect(Collectors.toUnmodifiableMap(
                            Map.Entry::getKey, entry -> List.copyOf(entry.getValue())));
            for (var entry : expectedFactAlternatives.entrySet()) {
                if (!expectedFacts.contains(entry.getKey()) || entry.getKey().isBlank()
                        || entry.getValue().isEmpty() || entry.getValue().stream().anyMatch(String::isBlank)) {
                    throw new IllegalArgumentException("AI_RAG_EVAL_FACT_ALTERNATIVES_INVALID");
                }
            }
        }
    }

    public record Dataset(String id, String name, String description, String agentKey, String status,
                          int caseCount, Instant createdAt, Instant updatedAt) { }

    public record KnowledgeBinding(String knowledgeBaseId, String indexReleaseId) { }

    public record EvaluationRun(
            String id, String datasetId, String agentKey, String agentVersionId, String ragPolicyVersionId,
            List<KnowledgeBinding> knowledgeBindings, String status, int totalCount, int passedCount,
            int failedCount, RagEvaluationMetrics.Summary metrics, String failureCode, String failureMessage,
            Instant createdAt, Instant startedAt, Instant finishedAt) {
        public EvaluationRun {
            knowledgeBindings = List.copyOf(knowledgeBindings);
        }

        public EvaluationRun withStatus(String nextStatus, Instant nextStartedAt, Instant nextFinishedAt) {
            return new EvaluationRun(id, datasetId, agentKey, agentVersionId, ragPolicyVersionId,
                    knowledgeBindings, nextStatus, totalCount, passedCount, failedCount, metrics,
                    failureCode, failureMessage, createdAt, nextStartedAt, nextFinishedAt);
        }
    }

    public record CaseResult(
            String id, String runId, String caseId, String debugRunId, String executionStatus,
            boolean passed, long latencyMs, String answerMode, String answerMarkdown,
            List<CustomerServiceRunEvent.Citation> citations, RagEvaluationMetrics.CaseMetrics metrics,
            String errorCode, String errorMessage, Instant createdAt) {
        public CaseResult {
            citations = List.copyOf(citations);
        }
    }
}
