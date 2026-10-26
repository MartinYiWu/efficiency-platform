package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import com.aiep.aihub.application.evaluation.RagEvaluationMetrics;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class RagEvaluationMetricsTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void passesOnlyWhenModeFactsSourcesCitationsAndVersionsAllMatch() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-1", "dataset-1", "AI-001", "是否允许开启 MAX？",
                "COMPANY_KNOWLEDGE", List.of("禁止开启 MAX", "人工审查"), List.of("允许开启 MAX"),
                List.of("研发内部AI使用规范"), List.of("version-2"), 1, List.of("制度", "禁止项"), true);

        var metrics = RagEvaluationMetrics.evaluate(testCase, response(
                "COMPANY_KNOWLEDGE", "规范明确禁止开启 MAX；AI 生成代码仍需人工审查。",
                "研发内部AI使用规范", "version-2"));

        assertThat(metrics.passed()).isTrue();
        assertThat(metrics.answerModeMatched()).isTrue();
        assertThat(metrics.expectedFactRecall()).isEqualTo(1.0);
        assertThat(metrics.prohibitedFactMatched()).isFalse();
        assertThat(metrics.sourceRecall()).isEqualTo(1.0);
        assertThat(metrics.citationCompliant()).isTrue();
        assertThat(metrics.versionMatched()).isTrue();
        assertThat(metrics.failures()).isEmpty();
    }

    @Test
    void reportsEveryQualityFailureWithoutTreatingExecutionAsFailed() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-2", "dataset-1", "AI-002", "怎么使用？", "COMPANY_KNOWLEDGE",
                List.of("禁止开启 MAX", "人工审查"), List.of("允许开启 MAX"),
                List.of("研发内部AI使用规范"), List.of("version-2"), 2, List.of(), true);

        var metrics = RagEvaluationMetrics.evaluate(testCase, response(
                "GENERAL_ADVICE", "允许开启 MAX。", "其他文档", "version-1"));

        assertThat(metrics.passed()).isFalse();
        assertThat(metrics.failures()).containsExactlyInAnyOrder(
                "ANSWER_MODE_MISMATCH", "EXPECTED_FACT_MISSING", "PROHIBITED_FACT_MATCHED",
                "EXPECTED_SOURCE_MISSING", "CITATION_COUNT_INSUFFICIENT", "VERSION_MISMATCH");
    }

    @Test
    void calculatesObservedLatencyPercentiles() {
        var summary = RagEvaluationMetrics.summarize(3,
                List.of(
                        new RagEvaluationMetrics.CaseMetrics(true, true, 1.0, false, 1.0, true, true, List.of()),
                        new RagEvaluationMetrics.CaseMetrics(false, true, .5, false, 1.0, true, true, List.of("EXPECTED_FACT_MISSING"))),
                List.of(100L, 200L, 300L, 400L));

        assertThat(summary.executionSuccessRate()).isEqualTo(2.0 / 3.0);
        assertThat(summary.answerModeAccuracy()).isEqualTo(1.0);
        assertThat(summary.casePassRate()).isEqualTo(1.0 / 3.0);
        assertThat(summary.expectedFactRecall()).isEqualTo(.75);
        assertThat(summary.prohibitedFactRate()).isZero();
        assertThat(summary.sourceRecallAtK()).isEqualTo(1.0);
        assertThat(summary.citationComplianceRate()).isEqualTo(1.0);
        assertThat(summary.versionAccuracy()).isEqualTo(1.0);
        assertThat(summary.latencyP50Ms()).isEqualTo(200);
        assertThat(summary.latencyP95Ms()).isEqualTo(400);
    }

    @Test
    void returnsZeroSummaryWhenEveryExternalCallFails() {
        var summary = RagEvaluationMetrics.summarize(2, List.of(), List.of());
        assertThat(summary.executionSuccessRate()).isZero();
        assertThat(summary.casePassRate()).isZero();
        assertThat(summary.expectedFactRecall()).isNull();
        assertThat(summary.latencyP50Ms()).isZero();
        assertThat(summary.latencyP95Ms()).isZero();
    }

    @Test
    void excludesNotApplicableExpectationsFromMetricDenominators() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-3", "dataset-1", "AI-003", "通用问题", "GENERAL_ADVICE",
                List.of(), List.of(), List.of(), List.of(), 0, List.of(), true);

        var metrics = RagEvaluationMetrics.evaluate(testCase, response(
                "GENERAL_ADVICE", "这是通用建议。", "其他文档", "version-1"));
        var summary = RagEvaluationMetrics.summarize(1, List.of(metrics), List.of(20L));

        assertThat(metrics.expectedFactRecall()).isNull();
        assertThat(metrics.prohibitedFactMatched()).isNull();
        assertThat(metrics.sourceRecall()).isNull();
        assertThat(metrics.citationCompliant()).isNull();
        assertThat(metrics.versionMatched()).isNull();
        assertThat(summary.expectedFactRecall()).isNull();
        assertThat(summary.prohibitedFactRate()).isNull();
        assertThat(summary.sourceRecallAtK()).isNull();
        assertThat(summary.citationComplianceRate()).isNull();
        assertThat(summary.versionAccuracy()).isNull();
    }

    @Test
    void rejectsCitationsOutsideTheFrozenIndexBindings() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-4", "dataset-1", "AI-004", "制度是什么？", "COMPANY_KNOWLEDGE",
                List.of("禁止开启 MAX"), List.of(), List.of("研发内部AI使用规范"),
                List.of("version-2"), 1, List.of(), true);

        var metrics = RagEvaluationMetrics.evaluate(testCase, response(
                "COMPANY_KNOWLEDGE", "禁止开启 MAX", "研发内部AI使用规范", "version-2"),
                Set.of("another-index"));

        assertThat(metrics.citationCompliant()).isFalse();
        assertThat(metrics.failures()).contains("CITATION_COUNT_INSUFFICIENT");
    }

    private CustomerServiceDebugView response(String mode, String answer, String title, String version) throws Exception {
        String json = """
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-1",
                 "status":"SUCCEEDED","stages":[],"answer_mode":"%s","answer_markdown":"%s",
                 "citations":[{"citation_no":1,"knowledge_base_id":"kb","document_id":"doc",
                   "document_version_id":"%s","index_release_id":"index","chunk_id":"chunk",
                   "document_title":"%s","version_no":2,"section_path":"规范","page_no":1,
                   "quoted_text":"原文","content_hash":"hash","parent_id":"parent",
                   "citation_type":"FULL_PARENT","original_spans":[{"start_offset":0,"end_offset":2,
                   "content_hash":"span"}]}],"error_code":null,"error_message":null}
                """.formatted(mode, answer, version, title);
        return mapper.readValue(json, CustomerServiceDebugView.class);
    }
}
