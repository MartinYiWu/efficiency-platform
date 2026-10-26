package com.aiep.aihub.application.evaluation;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

public final class RagEvaluationMetrics {
    private RagEvaluationMetrics() { }

    public static CaseMetrics evaluate(EvaluationCase testCase, CustomerServiceDebugView response) {
        return evaluate(testCase, response, Set.of());
    }

    public static CaseMetrics evaluate(EvaluationCase testCase, CustomerServiceDebugView response,
                                       Set<String> allowedIndexReleaseIds) {
        String answer = normalize(response.answerMarkdown());
        boolean answerModeMatched = testCase.expectedAnswerMode().equals(response.answerMode());
        long expectedFactHits = testCase.expectedFacts().stream()
                .map(RagEvaluationMetrics::normalize).filter(answer::contains).count();
        Double expectedFactRecall = testCase.expectedFacts().isEmpty()
                ? null : ratio(expectedFactHits, testCase.expectedFacts().size());
        Boolean prohibitedFactMatched = testCase.prohibitedFacts().isEmpty() ? null : testCase.prohibitedFacts().stream()
                .map(RagEvaluationMetrics::normalize).anyMatch(answer::contains);
        List<CustomerServiceRunEvent.Citation> citations = response.citations() == null ? List.of() : response.citations();
        Set<String> titles = citations.stream().map(item -> item.documentTitle()).collect(Collectors.toSet());
        long sourceHits = testCase.expectedDocumentTitles().stream().filter(titles::contains).count();
        Double sourceRecall = testCase.expectedDocumentTitles().isEmpty()
                ? null : ratio(sourceHits, testCase.expectedDocumentTitles().size());
        Boolean citationCompliant = testCase.minCitationCount() == 0 ? null : citations.size() >= testCase.minCitationCount()
                && citations.stream().allMatch(item -> item.documentVersionId() != null
                        && item.indexReleaseId() != null
                        && (allowedIndexReleaseIds.isEmpty() || allowedIndexReleaseIds.contains(item.indexReleaseId()))
                        && item.quotedText() != null && !item.quotedText().isBlank());
        Set<String> versions = citations.stream().map(item -> item.documentVersionId()).collect(Collectors.toSet());
        Boolean versionMatched = testCase.expectedDocumentVersionIds().isEmpty() ? null
                : versions.containsAll(testCase.expectedDocumentVersionIds());
        List<String> failures = new ArrayList<>();
        if (!answerModeMatched) failures.add("ANSWER_MODE_MISMATCH");
        if (expectedFactRecall != null && expectedFactRecall < 1) failures.add("EXPECTED_FACT_MISSING");
        if (Boolean.TRUE.equals(prohibitedFactMatched)) failures.add("PROHIBITED_FACT_MATCHED");
        if (sourceRecall != null && sourceRecall < 1) failures.add("EXPECTED_SOURCE_MISSING");
        if (Boolean.FALSE.equals(citationCompliant)) failures.add("CITATION_COUNT_INSUFFICIENT");
        if (Boolean.FALSE.equals(versionMatched)) failures.add("VERSION_MISMATCH");
        return new CaseMetrics(failures.isEmpty(), answerModeMatched, expectedFactRecall,
                prohibitedFactMatched, sourceRecall, citationCompliant, versionMatched, List.copyOf(failures));
    }

    public static Summary summarize(int totalCount, List<CaseMetrics> results, List<Long> latencyMs) {
        return new Summary(
                totalCount == 0 ? 0 : results.size() / (double) totalCount,
                averageBoolean(results.stream().map(CaseMetrics::answerModeMatched).toList()),
                averageDouble(results.stream().map(CaseMetrics::expectedFactRecall).toList()),
                averageBoolean(results.stream().map(CaseMetrics::prohibitedFactMatched).toList()),
                averageDouble(results.stream().map(CaseMetrics::sourceRecall).toList()),
                averageBoolean(results.stream().map(CaseMetrics::citationCompliant).toList()),
                averageBoolean(results.stream().map(CaseMetrics::versionMatched).toList()),
                totalCount == 0 ? 0 : results.stream().filter(CaseMetrics::passed).count() / (double) totalCount,
                percentile(latencyMs, .5), percentile(latencyMs, .95));
    }

    private static Double averageBoolean(List<Boolean> values) {
        List<Boolean> applicable = values.stream().filter(value -> value != null).toList();
        if (applicable.isEmpty()) return null;
        return applicable.stream().filter(Boolean.TRUE::equals).count() / (double) applicable.size();
    }

    private static Double averageDouble(List<Double> values) {
        return values.stream().filter(value -> value != null).mapToDouble(Double::doubleValue)
                .average().stream().boxed().findFirst().orElse(null);
    }

    private static long percentile(List<Long> values, double percentile) {
        if (values.isEmpty()) return 0;
        List<Long> sorted = values.stream().sorted(Comparator.naturalOrder()).toList();
        int index = Math.max(0, (int) Math.ceil(percentile * sorted.size()) - 1);
        return sorted.get(index);
    }

    private static double ratio(long hits, int total) {
        return total == 0 ? 1 : hits / (double) total;
    }

    private static String normalize(String value) {
        return value == null ? "" : value
                .replaceAll("\\\\([\\\\`*_{}\\[\\]()#+\\-.!<>])", "$1")
                .replaceAll("\\s+", "")
                .toLowerCase(Locale.ROOT);
    }

    public record CaseMetrics(
            boolean passed,
            boolean answerModeMatched,
            Double expectedFactRecall,
            Boolean prohibitedFactMatched,
            Double sourceRecall,
            Boolean citationCompliant,
            Boolean versionMatched,
            List<String> failures) { }

    public record Summary(
            double executionSuccessRate,
            Double answerModeAccuracy,
            Double expectedFactRecall,
            Double prohibitedFactRate,
            Double sourceRecallAtK,
            Double citationComplianceRate,
            Double versionAccuracy,
            double casePassRate,
            long latencyP50Ms,
            long latencyP95Ms) { }
}
