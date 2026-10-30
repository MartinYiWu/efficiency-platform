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

    @Test
    void acceptsExpectedVersionWhenAnswerAlsoCitesAnotherFrozenDocument() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-5", "dataset-1", "TEAM-003", "PR 有哪些要求？", "COMPANY_KNOWLEDGE",
                List.of("至少指定一名审查者"), List.of(), List.of("研发团队标准规范文档"),
                List.of("version-team"), 1, List.of(), true);
        CustomerServiceDebugView view = mapper.readValue("""
                {"contract_version":"customer-service-rag-debug-view/1","debug_run_id":"run-2",
                 "status":"SUCCEEDED","stages":[],"answer_mode":"COMPANY_KNOWLEDGE",
                 "answer_markdown":"至少指定一名审查者",
                 "citations":[
                   {"citation_no":1,"knowledge_base_id":"kb","document_id":"team",
                    "document_version_id":"version-team","index_release_id":"index","chunk_id":"chunk-1",
                    "document_title":"研发团队标准规范文档","version_no":1,"section_path":"PR","page_no":1,
                    "quoted_text":"原文","content_hash":"hash-1"},
                   {"citation_no":2,"knowledge_base_id":"kb","document_id":"ai",
                    "document_version_id":"version-ai","index_release_id":"index","chunk_id":"chunk-2",
                    "document_title":"研发内部AI使用规范","version_no":1,"section_path":"协作","page_no":1,
                    "quoted_text":"原文","content_hash":"hash-2"}],
                 "error_code":null,"error_message":null}
                """, CustomerServiceDebugView.class);

        var metrics = RagEvaluationMetrics.evaluate(testCase, view, Set.of("index"));

        assertThat(metrics.versionMatched()).isTrue();
        assertThat(metrics.passed()).isTrue();
    }

    @Test
    void treatsMarkdownEscapesAsFormattingWhenMatchingExpectedFacts() throws Exception {
        EvaluationCase testCase = new EvaluationCase(
                "case-6", "dataset-1", "AGENT-004", "群 ID 格式是什么？", "COMPANY_KNOWLEDGE",
                List.of("oc_开头"), List.of(), List.of("阿里多Agent"),
                List.of("version-agent"), 1, List.of(), true);

        var metrics = RagEvaluationMetrics.evaluate(testCase, response(
                "COMPANY_KNOWLEDGE", "飞书群 ID 要以 oc\\\\_ 开头。", "阿里多Agent", "version-agent"));

        assertThat(metrics.expectedFactRecall()).isEqualTo(1.0);
        assertThat(metrics.passed()).isTrue();
    }

    @Test
    void acceptsOnlyExplicitCompleteEquivalentFactsWhileKeepingOtherFactsRequired() throws Exception {
        EvaluationCase testCase = mapper.copy()
                .configure(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
                .readValue("""
                {"id":"case-equivalent","datasetId":"dataset-1","caseNo":"FORMAT-001",
                 "question":"路由配置？","expectedAnswerMode":"COMPANY_KNOWLEDGE",
                 "expectedFacts":["route.type+route.key","禁止使用别名"],"prohibitedFacts":[],
                 "expectedDocumentTitles":[],"expectedDocumentVersionIds":[],"minCitationCount":0,
                 "tags":[],"enabled":true,
                 "expectedFactAlternatives":{"route.type+route.key":["route 采用 type + key 的结构"]}}
                """, EvaluationCase.class);
        var accepted = RagEvaluationMetrics.evaluate(testCase, response("COMPANY_KNOWLEDGE",
                "route 采用 type + key 的结构；禁止使用别名。", "规范", "v1"));
        assertThat(accepted.passed()).isTrue();
        assertThat(accepted.expectedFactRecall()).isEqualTo(1.0);
        for (String answer : List.of("type key；禁止使用别名", "route 采用 type + name 的结构；禁止使用别名",
                "route 采用 type + key 的结构")) {
            var rejected = RagEvaluationMetrics.evaluate(testCase,
                    response("COMPANY_KNOWLEDGE", answer, "规范", "v1"));
            assertThat(rejected.passed()).as(answer).isFalse();
            assertThat(rejected.failures()).contains("EXPECTED_FACT_MISSING");
        }
    }

    @Test
    void equivalentProhibitedFactStillRejectsTheAnswer() throws Exception {
        EvaluationCase testCase = new EvaluationCase("id", "dataset", "RULE-001", "要求？", "COMPANY_KNOWLEDGE",
                List.of("禁止绕过审核"), List.of("禁止绕过审核"), List.of(), List.of(), 0, List.of(), true,
                java.util.Map.of("禁止绕过审核", List.of("必须经过人工审批")));
        var metrics = RagEvaluationMetrics.evaluate(testCase,
                response("COMPANY_KNOWLEDGE", "必须经过人工审批", "规范", "v1"));
        assertThat(metrics.expectedFactRecall()).isEqualTo(1.0);
        assertThat(metrics.prohibitedFactMatched()).isTrue();
        assertThat(metrics.failures()).containsExactly("PROHIBITED_FACT_MATCHED");
    }

    @Test
    void rejectsUnboundOrBlankEquivalentFacts() {
        for (var alternatives : List.of(java.util.Map.of("其他事实", List.of("表述")),
                java.util.Map.of("原事实", List.of(" ")), java.util.Map.of("原事实", List.<String>of()))) {
            org.assertj.core.api.Assertions.assertThatThrownBy(() -> new EvaluationCase("id", "dataset", "RULE-002",
                    "要求？", "COMPANY_KNOWLEDGE", List.of("原事实"), List.of(), List.of(), List.of(), 0,
                    List.of(), true, alternatives)).isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void replaysHistoricalAnswerWithoutChangingLegacyLiteralScoring() throws Exception {
        var facts = List.of("peer.kind+peer.id", "oc_开头", "chatId", "替代");
        var legacy = new EvaluationCase("historical", "dataset", "AGENT-004", "peer？", "COMPANY_KNOWLEDGE",
                facts, List.of(), List.of(), List.of(), 0, List.of(), true);
        var node = mapper.valueToTree(response("COMPANY_KNOWLEDGE", "placeholder", "规范", "v1"));
        ((com.fasterxml.jackson.databind.node.ObjectNode) node).put("answer_markdown", "## peer 的填写方式\n\npeer 采用 kind + id 的结构填写：kind 表示会话类型，\"group\" 为群聊，\"user\" 为单聊；id 填写对应的飞书群ID或用户ID，不可用 chatId 替代。[1]\n\n路由绑定配置示例中，peer 写作 {\"kind\": \"group\", \"id\": \"oc_你的飞书群ID\"}，并与 channel: \"feishu\" 配合使用。[2][3][4]\n\n## 飞书群ID的格式要求\n\n飞书群ID（peer.id）的格式为以 oc_ 开头的字符串，需准确复制，后续路由配置核心依赖此ID。[5][6][7]");
        var historicalResponse = mapper.treeToValue(node, CustomerServiceDebugView.class);
        assertThat(RagEvaluationMetrics.evaluate(legacy, historicalResponse).expectedFactRecall()).isEqualTo(0.75);
        var explicit = new EvaluationCase(legacy.id(), legacy.datasetId(), legacy.caseNo(), legacy.question(),
                legacy.expectedAnswerMode(), facts, List.of(), List.of(), List.of(), 0, List.of(), true,
                java.util.Map.of("peer.kind+peer.id", List.of("peer 采用 kind + id 的结构填写")));
        assertThat(RagEvaluationMetrics.evaluate(explicit, historicalResponse).expectedFactRecall()).isEqualTo(1.0);
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
