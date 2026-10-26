package com.aiep.aihub.repository.customer;

import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcCustomerServiceMappers implements CustomerServiceMappers {
    private final JdbcTemplate jdbc;

    public JdbcCustomerServiceMappers(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Override public void insertConversation(ConversationPO v) {
        jdbc.update("INSERT INTO ai_customer_service_conversation "
                + "(id,tenant_id,user_id,title,status,last_message_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                v.id(), v.tenantId(), v.userId(), v.title(), v.status(), ts(v.lastMessageAt()), ts(v.createdAt()), ts(v.updatedAt()));
    }
    @Override public ConversationPO findConversation(String id, String tenantId, String userId) {
        return one("SELECT * FROM ai_customer_service_conversation WHERE id=? AND tenant_id=? AND user_id=? AND status<>'DELETED'",
                JdbcCustomerServiceMappers::conversation, id, tenantId, userId);
    }
    @Override public List<ConversationPO> listConversations(String tenantId, String userId, String keyword, int offset, int limit) {
        String like = keyword == null ? "%" : "%" + keyword + "%";
        return jdbc.query("SELECT * FROM ai_customer_service_conversation WHERE tenant_id=? AND user_id=? AND status<>'DELETED' AND title LIKE ? "
                + "ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT ? OFFSET ?",
                JdbcCustomerServiceMappers::conversation, tenantId, userId, like, limit, offset);
    }
    @Override public long countConversations(String tenantId, String userId, String keyword) {
        String like = keyword == null ? "%" : "%" + keyword + "%";
        return jdbc.queryForObject("SELECT COUNT(*) FROM ai_customer_service_conversation WHERE tenant_id=? AND user_id=? AND status<>'DELETED' AND title LIKE ?",
                Long.class, tenantId, userId, like);
    }
    @Override public void updateConversation(String id, String tenantId, String userId, String title, String status) {
        jdbc.update("UPDATE ai_customer_service_conversation SET title=COALESCE(?,title),status=COALESCE(?,status),updated_at=NOW(6) "
                + "WHERE id=? AND tenant_id=? AND user_id=?", title, status, id, tenantId, userId);
    }
    @Override public void touchConversation(String id, String title) {
        jdbc.update("UPDATE ai_customer_service_conversation SET title=COALESCE(NULLIF(title,''),?),last_message_at=NOW(6),updated_at=NOW(6) WHERE id=?", title, id);
    }

    @Override public void insertMessage(MessagePO v) {
        jdbc.update("INSERT INTO ai_customer_service_message "
                + "(id,conversation_id,tenant_id,role,content_markdown,status,answer_mode,run_id,client_request_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.conversationId(), v.tenantId(), v.role(), v.content(), v.status(), v.answerMode(), v.runId(), v.clientRequestId(), ts(v.createdAt()));
    }
    @Override public MessagePO findMessage(String id, String tenantId) {
        return one("SELECT * FROM ai_customer_service_message WHERE id=? AND tenant_id=?", JdbcCustomerServiceMappers::message, id, tenantId);
    }
    @Override public MessagePO findMessageByClientRequest(String tenantId, String clientRequestId) {
        return one("SELECT * FROM ai_customer_service_message WHERE tenant_id=? AND client_request_id=?", JdbcCustomerServiceMappers::message, tenantId, clientRequestId);
    }
    @Override public MessagePO findAssistantMessageByRun(String runId, String tenantId) {
        return one("SELECT * FROM ai_customer_service_message WHERE run_id=? AND tenant_id=? AND role='ASSISTANT'", JdbcCustomerServiceMappers::message, runId, tenantId);
    }
    @Override public List<MessagePO> listMessages(String conversationId, String tenantId, String beforeMessageId, int limit) {
        if (beforeMessageId == null) {
            return jdbc.query("SELECT * FROM ai_customer_service_message WHERE conversation_id=? AND tenant_id=? ORDER BY created_at DESC LIMIT ?",
                    JdbcCustomerServiceMappers::message, conversationId, tenantId, limit);
        }
        return jdbc.query("SELECT * FROM ai_customer_service_message WHERE conversation_id=? AND tenant_id=? "
                        + "AND created_at < (SELECT created_at FROM ai_customer_service_message WHERE id=?) ORDER BY created_at DESC LIMIT ?",
                JdbcCustomerServiceMappers::message, conversationId, tenantId, beforeMessageId, limit);
    }
    @Override public List<MessagePO> listCompletedHistory(String conversationId, String tenantId, int limit) {
        return jdbc.query("SELECT * FROM (SELECT * FROM ai_customer_service_message WHERE conversation_id=? AND tenant_id=? "
                        + "AND status='COMPLETED' ORDER BY created_at DESC LIMIT ?) x ORDER BY created_at",
                JdbcCustomerServiceMappers::message, conversationId, tenantId, limit);
    }
    @Override public void completeAssistantMessage(String id, String content, String answerMode, String status) {
        jdbc.update("UPDATE ai_customer_service_message SET content_markdown=?,answer_mode=?,status=? WHERE id=?", content, answerMode, status, id);
    }

    @Override public void insertRun(RunPO v) {
        jdbc.update("INSERT INTO ai_customer_service_run "
                + "(id,conversation_id,tenant_id,user_message_id,agent_run_id,agent_release_id,status,answer_mode,last_event_sequence,"
                + "failure_code,failure_message,started_at,finished_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.conversationId(), v.tenantId(), v.userMessageId(), v.agentRunId(), v.agentReleaseId(), v.status(), v.answerMode(),
                v.lastEventSequence(), v.failureCode(), v.failureMessage(), ts(v.startedAt()), ts(v.finishedAt()), ts(v.createdAt()), ts(v.updatedAt()));
    }
    @Override public RunPO findRun(String id, String tenantId) {
        return one("SELECT * FROM ai_customer_service_run WHERE id=? AND tenant_id=?", JdbcCustomerServiceMappers::run, id, tenantId);
    }
    @Override public RunPO findRunByUserMessage(String userMessageId, String tenantId) {
        return one("SELECT * FROM ai_customer_service_run WHERE user_message_id=? AND tenant_id=?", JdbcCustomerServiceMappers::run, userMessageId, tenantId);
    }
    @Override public void bindAgentRun(String id, String agentRunId, String status) {
        jdbc.update("UPDATE ai_customer_service_run SET agent_run_id=?,status=?,started_at=NOW(6),updated_at=NOW(6) WHERE id=?", agentRunId, status, id);
    }
    @Override public boolean advanceRun(String id, long expectedSequence, long nextSequence, String status, String answerMode, String failureCode, String failureMessage) {
        return jdbc.update("UPDATE ai_customer_service_run SET last_event_sequence=?,status=?,answer_mode=COALESCE(?,answer_mode),"
                        + "failure_code=?,failure_message=?,finished_at=IF(? IN ('SUCCEEDED','FAILED','TIMED_OUT','CANCELLED'),NOW(6),finished_at),updated_at=NOW(6) "
                        + "WHERE id=? AND last_event_sequence=? AND status NOT IN ('SUCCEEDED','FAILED','TIMED_OUT','CANCELLED')",
                nextSequence, status, answerMode, failureCode, failureMessage, status, id, expectedSequence) == 1;
    }
    @Override public List<RunPO> listRuns(String agentKey, String status, String answerMode, int offset, int limit) {
        return jdbc.query("SELECT r.* FROM ai_customer_service_run r JOIN ai_agent_release a ON a.id=r.agent_release_id "
                        + "JOIN ai_agent_definition d ON d.id=a.agent_definition_id WHERE (? IS NULL OR d.agent_key=?) "
                        + "AND (? IS NULL OR r.status=?) AND (? IS NULL OR r.answer_mode=?) ORDER BY r.created_at DESC LIMIT ? OFFSET ?",
                JdbcCustomerServiceMappers::run, agentKey, agentKey, status, status, answerMode, answerMode, limit, offset);
    }
    @Override public long countRuns(String agentKey, String status, String answerMode) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM ai_customer_service_run r JOIN ai_agent_release a ON a.id=r.agent_release_id "
                        + "JOIN ai_agent_definition d ON d.id=a.agent_definition_id WHERE (? IS NULL OR d.agent_key=?) "
                        + "AND (? IS NULL OR r.status=?) AND (? IS NULL OR r.answer_mode=?)", Long.class,
                agentKey, agentKey, status, status, answerMode, answerMode);
    }

    @Override public void insertRunStep(RunStepPO v) {
        jdbc.update("INSERT IGNORE INTO ai_customer_service_run_step "
                + "(id,run_id,sequence_no,stage,status,public_summary,internal_payload,started_at,finished_at) VALUES (?,?,?,?,?,?,CAST(? AS JSON),?,?)",
                v.id(), v.runId(), v.sequenceNo(), v.stage(), v.status(), v.publicSummary(), v.internalPayload(), ts(v.startedAt()), ts(v.finishedAt()));
    }
    @Override public List<RunStepPO> listRunSteps(String runId) {
        return jdbc.query("SELECT * FROM ai_customer_service_run_step WHERE run_id=? ORDER BY sequence_no", JdbcCustomerServiceMappers::step, runId);
    }
    @Override public void insertCitation(CitationPO v) {
        jdbc.update("INSERT IGNORE INTO ai_customer_service_citation "
                + "(id,run_id,message_id,citation_no,knowledge_base_id,document_id,document_version_id,index_release_id,chunk_id,"
                + "document_title,version_no,section_path,page_no,quoted_text,content_hash,created_at,parent_id,citation_type,original_spans_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CAST(? AS JSON))",
                v.id(), v.runId(), v.messageId(), v.citationNo(), v.knowledgeBaseId(), v.documentId(), v.documentVersionId(), v.indexReleaseId(),
                v.chunkId(), v.documentTitle(), v.versionNo(), v.sectionPath(), v.pageNo(), v.quotedText(), v.contentHash(), ts(v.createdAt()),
                v.parentId(), v.citationType(), spansJson(v.originalSpans()));
    }
    @Override public List<CitationPO> listCitationsByMessage(String messageId) {
        return jdbc.query("SELECT * FROM ai_customer_service_citation WHERE message_id=? ORDER BY citation_no", JdbcCustomerServiceMappers::citation, messageId);
    }
    @Override public CitationPO findCitationByRunAndNumber(String runId, int citationNo) {
        return one("SELECT * FROM ai_customer_service_citation WHERE run_id=? AND citation_no=?", JdbcCustomerServiceMappers::citation, runId, citationNo);
    }
    @Override public CitationPO findCitation(String id, String tenantId) {
        return one("SELECT c.* FROM ai_customer_service_citation c JOIN ai_customer_service_run r ON r.id=c.run_id WHERE c.id=? AND r.tenant_id=?",
                JdbcCustomerServiceMappers::citation, id, tenantId);
    }

    @Override public void upsertFeedback(FeedbackPO v) {
        jdbc.update("INSERT INTO ai_customer_service_feedback (id,conversation_id,message_id,run_id,tenant_id,user_id,rating,reason_code,comment,created_at,updated_at) "
                        + "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE rating=VALUES(rating),reason_code=VALUES(reason_code),comment=VALUES(comment),updated_at=VALUES(updated_at)",
                v.id(), v.conversationId(), v.messageId(), v.runId(), v.tenantId(), v.userId(), v.rating(), v.reasonCode(), v.comment(), ts(v.createdAt()), ts(v.updatedAt()));
    }
    @Override public FeedbackPO findFeedback(String tenantId, String userId, String messageId) {
        return one("SELECT * FROM ai_customer_service_feedback WHERE tenant_id=? AND user_id=? AND message_id=?", JdbcCustomerServiceMappers::feedback, tenantId, userId, messageId);
    }
    @Override public List<FeedbackPO> listFeedback(String rating, String reasonCode, int offset, int limit) {
        return jdbc.query("SELECT * FROM ai_customer_service_feedback WHERE (? IS NULL OR rating=?) AND (? IS NULL OR reason_code=?) ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                JdbcCustomerServiceMappers::feedback, rating, rating, reasonCode, reasonCode, limit, offset);
    }
    @Override public long countFeedback(String rating, String reasonCode) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM ai_customer_service_feedback WHERE (? IS NULL OR rating=?) AND (? IS NULL OR reason_code=?)",
                Long.class, rating, rating, reasonCode, reasonCode);
    }

    private <T> T one(String sql, org.springframework.jdbc.core.RowMapper<T> mapper, Object... args) {
        try { return jdbc.queryForObject(sql, mapper, args); }
        catch (EmptyResultDataAccessException ignored) { return null; }
    }
    private static Instant instant(ResultSet r, String name) throws SQLException { Timestamp v = r.getTimestamp(name); return v == null ? null : v.toInstant(); }
    private static Timestamp ts(Instant value) { return value == null ? null : Timestamp.from(value); }
    private static ConversationPO conversation(ResultSet r, int n) throws SQLException { return new ConversationPO(r.getString("id"),r.getString("tenant_id"),r.getString("user_id"),r.getString("title"),r.getString("status"),instant(r,"last_message_at"),instant(r,"created_at"),instant(r,"updated_at")); }
    private static MessagePO message(ResultSet r, int n) throws SQLException { return new MessagePO(r.getString("id"),r.getString("conversation_id"),r.getString("tenant_id"),r.getString("role"),r.getString("content_markdown"),r.getString("status"),r.getString("answer_mode"),r.getString("run_id"),r.getString("client_request_id"),instant(r,"created_at")); }
    private static RunPO run(ResultSet r, int n) throws SQLException { return new RunPO(r.getString("id"),r.getString("conversation_id"),r.getString("tenant_id"),r.getString("user_message_id"),r.getString("agent_run_id"),r.getString("agent_release_id"),r.getString("status"),r.getString("answer_mode"),r.getLong("last_event_sequence"),r.getString("failure_code"),r.getString("failure_message"),instant(r,"started_at"),instant(r,"finished_at"),instant(r,"created_at"),instant(r,"updated_at")); }
    private static RunStepPO step(ResultSet r, int n) throws SQLException { return new RunStepPO(r.getString("id"),r.getString("run_id"),r.getLong("sequence_no"),r.getString("stage"),r.getString("status"),r.getString("public_summary"),r.getString("internal_payload"),instant(r,"started_at"),instant(r,"finished_at")); }
    private static CitationPO citation(ResultSet r, int n) throws SQLException { return new CitationPO(r.getString("id"),r.getString("run_id"),r.getString("message_id"),r.getInt("citation_no"),r.getString("knowledge_base_id"),r.getString("document_id"),r.getString("document_version_id"),r.getString("index_release_id"),r.getString("chunk_id"),r.getString("document_title"),r.getInt("version_no"),r.getString("section_path"),(Integer)r.getObject("page_no"),r.getString("quoted_text"),r.getString("content_hash"),instant(r,"created_at"),r.getString("parent_id"),r.getString("citation_type"),readSpans(r.getString("original_spans_json"))); }

    private static String spansJson(java.util.List<com.aiep.platformai.api.dto.CustomerServiceEvidenceFacts.Span> spans) {
        if (spans == null) return null;
        try { return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(spans); }
        catch (com.fasterxml.jackson.core.JsonProcessingException error) { throw new IllegalArgumentException("CITATION_SPANS_INVALID", error); }
    }

    private static java.util.List<com.aiep.platformai.api.dto.CustomerServiceEvidenceFacts.Span> readSpans(String json) {
        if (json == null) return null;
        try { return new com.fasterxml.jackson.databind.ObjectMapper().readValue(json, new com.fasterxml.jackson.core.type.TypeReference<>() { }); }
        catch (com.fasterxml.jackson.core.JsonProcessingException error) { throw new IllegalArgumentException("CITATION_SPANS_INVALID", error); }
    }
    private static FeedbackPO feedback(ResultSet r, int n) throws SQLException { return new FeedbackPO(r.getString("id"),r.getString("conversation_id"),r.getString("message_id"),r.getString("run_id"),r.getString("tenant_id"),r.getString("user_id"),r.getString("rating"),r.getString("reason_code"),r.getString("comment"),instant(r,"created_at"),instant(r,"updated_at")); }
}
