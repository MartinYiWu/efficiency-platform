package com.aiep.aihub.repository.evaluation;

import com.aiep.aihub.application.evaluation.RagEvaluationMetrics;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.CaseResult;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.Dataset;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationCase;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.EvaluationRun;
import com.aiep.aihub.application.evaluation.RagEvaluationModels.KnowledgeBinding;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcRagEvaluationRepository implements RagEvaluationRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public JdbcRagEvaluationRepository(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Override
    public Dataset createDataset(Dataset value) {
        jdbc.update("INSERT INTO ai_rag_eval_dataset(id,name,description,agent_key,status,created_by,created_at,updated_at) VALUES(?,?,?,?,?,'1',?,?)",
                value.id(), value.name(), value.description(), value.agentKey(), value.status(),
                timestamp(value.createdAt()), timestamp(value.updatedAt()));
        return value;
    }

    @Override
    public List<Dataset> listDatasets() {
        return jdbc.query("SELECT d.*,(SELECT COUNT(*) FROM ai_rag_eval_case c WHERE c.dataset_id=d.id) case_count FROM ai_rag_eval_dataset d ORDER BY d.updated_at DESC",
                (rs, row) -> dataset(rs));
    }

    @Override
    public Dataset findDataset(String id) {
        return jdbc.query("SELECT d.*,(SELECT COUNT(*) FROM ai_rag_eval_case c WHERE c.dataset_id=d.id) case_count FROM ai_rag_eval_dataset d WHERE d.id=?",
                rs -> rs.next() ? dataset(rs) : null, id);
    }

    @Override
    public int upsertCases(String datasetId, List<EvaluationCase> values) {
        int changed = 0;
        for (EvaluationCase value : values) {
            changed += jdbc.update("""
                    INSERT INTO ai_rag_eval_case(id,dataset_id,case_no,question,expected_answer_mode,expected_facts,
                    prohibited_facts,expected_document_titles,expected_document_version_ids,min_citation_count,tags,
                    enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON DUPLICATE KEY UPDATE question=VALUES(question),expected_answer_mode=VALUES(expected_answer_mode),
                    expected_facts=VALUES(expected_facts),prohibited_facts=VALUES(prohibited_facts),
                    expected_document_titles=VALUES(expected_document_titles),expected_document_version_ids=VALUES(expected_document_version_ids),
                    min_citation_count=VALUES(min_citation_count),tags=VALUES(tags),enabled=VALUES(enabled),updated_at=VALUES(updated_at)
                    """, value.id(), datasetId, value.caseNo(), value.question(), value.expectedAnswerMode(),
                    json(value.expectedFacts()), json(value.prohibitedFacts()), json(value.expectedDocumentTitles()),
                    json(value.expectedDocumentVersionIds()), value.minCitationCount(), json(value.tags()), value.enabled(),
                    Timestamp.from(Instant.now()), Timestamp.from(Instant.now()));
        }
        return changed;
    }

    @Override
    public List<EvaluationCase> listCases(String datasetId) {
        return jdbc.query("SELECT * FROM ai_rag_eval_case WHERE dataset_id=? ORDER BY case_no",
                (rs, row) -> evaluationCase(rs), datasetId);
    }

    @Override
    public List<EvaluationCase> listEnabledCases(String datasetId) {
        return jdbc.query("SELECT * FROM ai_rag_eval_case WHERE dataset_id=? AND enabled=1 ORDER BY case_no",
                (rs, row) -> evaluationCase(rs), datasetId);
    }

    @Override
    public EvaluationRun createRun(EvaluationRun value) {
        jdbc.update("""
                INSERT INTO ai_rag_eval_run(id,dataset_id,agent_key,agent_version_id,rag_policy_version_id,
                knowledge_bindings,status,total_count,passed_count,failed_count,metrics_json,failure_code,failure_message,
                created_by,created_at,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'1',?,?,?)
                """, value.id(), value.datasetId(), value.agentKey(), value.agentVersionId(), value.ragPolicyVersionId(),
                json(value.knowledgeBindings()), value.status(), value.totalCount(), value.passedCount(), value.failedCount(),
                null, value.failureCode(), value.failureMessage(), timestamp(value.createdAt()), null, null);
        return value;
    }

    @Override
    public void markRunning(String id, Instant startedAt) {
        jdbc.update("UPDATE ai_rag_eval_run SET status='RUNNING',started_at=? WHERE id=?", timestamp(startedAt), id);
    }

    @Override
    public void saveResult(CaseResult value) {
        jdbc.update("""
                INSERT INTO ai_rag_eval_case_result(id,run_id,case_id,debug_run_id,execution_status,passed,latency_ms,
                answer_mode,answer_markdown,citations_json,metrics_json,error_code,error_message,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, value.id(), value.runId(), value.caseId(), value.debugRunId(), value.executionStatus(), value.passed(),
                value.latencyMs(), value.answerMode(), value.answerMarkdown(), json(value.citations()), json(value.metrics()),
                value.errorCode(), value.errorMessage(), timestamp(value.createdAt()));
    }

    @Override
    public void completeRun(EvaluationRun value) {
        jdbc.update("UPDATE ai_rag_eval_run SET status=?,passed_count=?,failed_count=?,metrics_json=?,failure_code=?,failure_message=?,started_at=?,finished_at=? WHERE id=?",
                value.status(), value.passedCount(), value.failedCount(), json(value.metrics()), value.failureCode(),
                value.failureMessage(), timestamp(value.startedAt()), timestamp(value.finishedAt()), value.id());
    }

    @Override
    public EvaluationRun findRun(String id) {
        return jdbc.query("SELECT * FROM ai_rag_eval_run WHERE id=?", rs -> rs.next() ? evaluationRun(rs) : null, id);
    }

    @Override
    public List<EvaluationRun> listRuns(String datasetId) {
        return jdbc.query("SELECT * FROM ai_rag_eval_run WHERE dataset_id=? ORDER BY created_at DESC",
                (rs, row) -> evaluationRun(rs), datasetId);
    }

    @Override
    public List<CaseResult> listResults(String runId) {
        return jdbc.query("SELECT * FROM ai_rag_eval_case_result WHERE run_id=? ORDER BY created_at",
                (rs, row) -> caseResult(rs), runId);
    }

    private Dataset dataset(ResultSet rs) throws SQLException {
        return new Dataset(rs.getString("id"), rs.getString("name"), rs.getString("description"),
                rs.getString("agent_key"), rs.getString("status"), rs.getInt("case_count"),
                instant(rs, "created_at"), instant(rs, "updated_at"));
    }

    private EvaluationCase evaluationCase(ResultSet rs) throws SQLException {
        return new EvaluationCase(rs.getString("id"), rs.getString("dataset_id"), rs.getString("case_no"),
                rs.getString("question"), rs.getString("expected_answer_mode"), strings(rs.getString("expected_facts")),
                strings(rs.getString("prohibited_facts")), strings(rs.getString("expected_document_titles")),
                strings(rs.getString("expected_document_version_ids")), rs.getInt("min_citation_count"),
                strings(rs.getString("tags")), rs.getBoolean("enabled"));
    }

    private EvaluationRun evaluationRun(ResultSet rs) throws SQLException {
        return new EvaluationRun(rs.getString("id"), rs.getString("dataset_id"), rs.getString("agent_key"),
                rs.getString("agent_version_id"), rs.getString("rag_policy_version_id"),
                read(rs.getString("knowledge_bindings"), new TypeReference<List<KnowledgeBinding>>() {}),
                rs.getString("status"), rs.getInt("total_count"), rs.getInt("passed_count"), rs.getInt("failed_count"),
                readNullable(rs.getString("metrics_json"), RagEvaluationMetrics.Summary.class), rs.getString("failure_code"),
                rs.getString("failure_message"), instant(rs, "created_at"), instant(rs, "started_at"), instant(rs, "finished_at"));
    }

    private CaseResult caseResult(ResultSet rs) throws SQLException {
        return new CaseResult(rs.getString("id"), rs.getString("run_id"), rs.getString("case_id"),
                rs.getString("debug_run_id"), rs.getString("execution_status"), rs.getBoolean("passed"),
                rs.getLong("latency_ms"), rs.getString("answer_mode"), rs.getString("answer_markdown"),
                readNullableList(rs.getString("citations_json")), readNullable(rs.getString("metrics_json"), RagEvaluationMetrics.CaseMetrics.class),
                rs.getString("error_code"), rs.getString("error_message"), instant(rs, "created_at"));
    }

    private List<String> strings(String value) { return read(value, new TypeReference<List<String>>() {}); }
    private List<CustomerServiceRunEvent.Citation> readNullableList(String value) {
        return value == null ? List.of() : read(value, new TypeReference<List<CustomerServiceRunEvent.Citation>>() {});
    }
    private <T> T read(String value, TypeReference<T> type) {
        try { return mapper.readValue(normalizeJson(value), type); }
        catch (JsonProcessingException error) { throw new IllegalStateException("AI_RAG_EVAL_JSON_INVALID", error); }
    }
    private <T> T readNullable(String value, Class<T> type) {
        if (value == null) return null;
        try { return mapper.readValue(normalizeJson(value), type); }
        catch (JsonProcessingException error) { throw new IllegalStateException("AI_RAG_EVAL_JSON_INVALID", error); }
    }
    private String json(Object value) {
        if (value == null) return null;
        try { return mapper.writeValueAsString(value); }
        catch (JsonProcessingException error) { throw new IllegalArgumentException("AI_RAG_EVAL_JSON_INVALID", error); }
    }
    private static Timestamp timestamp(Instant value) { return value == null ? null : Timestamp.from(value); }
    private String normalizeJson(String value) throws JsonProcessingException {
        var node = mapper.readTree(value);
        return node.isTextual() ? node.textValue() : value;
    }
    private static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp value = rs.getTimestamp(column);
        return value == null ? null : value.toInstant();
    }
}
