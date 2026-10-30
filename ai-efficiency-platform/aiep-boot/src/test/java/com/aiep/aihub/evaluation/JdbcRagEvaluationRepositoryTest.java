package com.aiep.aihub.evaluation;

import static org.assertj.core.api.Assertions.assertThat;

import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.repository.evaluation.JdbcRagEvaluationRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;

class JdbcRagEvaluationRepositoryTest {

    @Test
    void storesDatasetAndIdempotentlyUpdatesCasesByCaseNumber() {
        var database = new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.H2)
                .setName("rag-eval;MODE=MySQL;DATABASE_TO_LOWER=TRUE").build();
        try {
            JdbcTemplate jdbc = new JdbcTemplate(database);
            jdbc.execute("""
                    CREATE TABLE ai_rag_eval_dataset(id VARCHAR(36) PRIMARY KEY,name VARCHAR(255),description VARCHAR(2000),
                    agent_key VARCHAR(128),status VARCHAR(32),created_by VARCHAR(64),created_at TIMESTAMP,updated_at TIMESTAMP)
                    """);
            jdbc.execute("""
                    CREATE TABLE ai_rag_eval_case(id VARCHAR(36) PRIMARY KEY,dataset_id VARCHAR(36),case_no VARCHAR(128),
                    question VARCHAR(4000),expected_answer_mode VARCHAR(32),expected_facts JSON,prohibited_facts JSON,
                    expected_document_titles JSON,expected_document_version_ids JSON,min_citation_count INT,tags JSON,
                    enabled BOOLEAN,created_at TIMESTAMP,updated_at TIMESTAMP,UNIQUE(dataset_id,case_no))
                    """);
            var repository = new JdbcRagEvaluationRepository(jdbc, new ObjectMapper());
            Instant now = Instant.parse("2026-10-26T00:00:00Z");
            repository.createDataset(new Dataset("d1", "规范", "说明", "customer-service", "ACTIVE", 0, now, now));
            repository.upsertCases("d1", List.of(caseValue("c1", "原问题")));
            repository.upsertCases("d1", List.of(caseValue("c2", "更新问题")));

            assertThat(repository.listDatasets()).singleElement().satisfies(dataset -> {
                assertThat(dataset.id()).isEqualTo("d1");
                assertThat(dataset.caseCount()).isEqualTo(1);
            });
            assertThat(repository.listEnabledCases("d1")).singleElement().satisfies(testCase -> {
                assertThat(testCase.id()).isEqualTo("c1");
                assertThat(testCase.question()).isEqualTo("更新问题");
                assertThat(testCase.expectedFacts()).containsExactly("事实一");
                assertThat(testCase.tags()).containsExactly("制度");
            });
            EvaluationCase original = repository.listCases("d1").getFirst();
            assertThat(original.expectedFactAlternatives()).isEmpty();
            var alternatives = java.util.Map.of("事实一", List.of("事实一的完整等价表述"));
            repository.upsertCases("d1", List.of(new EvaluationCase(original.id(), "d1", "C-001", "等价问题",
                    original.expectedAnswerMode(), original.expectedFacts(), original.prohibitedFacts(),
                    original.expectedDocumentTitles(), original.expectedDocumentVersionIds(),
                    original.minCitationCount(), original.tags(), true, alternatives)));
            assertThat(repository.listCases("d1")).singleElement().satisfies(testCase -> {
                assertThat(testCase.expectedFacts()).containsExactly("事实一");
                assertThat(testCase.expectedFactAlternatives()).isEqualTo(alternatives);
            });
            repository.upsertCases("d1", List.of(original));
            assertThat(repository.listCases("d1").getFirst().expectedFactAlternatives()).isEmpty();
        } finally {
            database.shutdown();
        }
    }

    private EvaluationCase caseValue(String id, String question) {
        return new EvaluationCase(id, "d1", "C-001", question, "COMPANY_KNOWLEDGE",
                List.of("事实一"), List.of("错误一"), List.of("规范"), List.of(), 1,
                List.of("制度"), true);
    }
}
