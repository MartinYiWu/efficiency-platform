package com.aiep.knowledge.repository;

import java.util.ArrayList;
import java.util.List;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcKnowledgeMappers implements KnowledgeMappers {
    private static final DataClassRowMapper<KnowledgeBasePO> BASE_ROW = DataClassRowMapper.newInstance(KnowledgeBasePO.class);
    private static final DataClassRowMapper<KnowledgeDirectoryPO> DIRECTORY_ROW = DataClassRowMapper.newInstance(KnowledgeDirectoryPO.class);
    private static final DataClassRowMapper<KnowledgeDocumentPO> DOCUMENT_ROW = DataClassRowMapper.newInstance(KnowledgeDocumentPO.class);
    private static final DataClassRowMapper<KnowledgeDocumentVersionPO> VERSION_ROW = DataClassRowMapper.newInstance(KnowledgeDocumentVersionPO.class);
    private static final DataClassRowMapper<KnowledgeIngestBatchPO> BATCH_ROW = DataClassRowMapper.newInstance(KnowledgeIngestBatchPO.class);
    private static final DataClassRowMapper<KnowledgeIngestItemPO> ITEM_ROW = DataClassRowMapper.newInstance(KnowledgeIngestItemPO.class);
    private static final DataClassRowMapper<KnowledgeProcessingTaskPO> TASK_ROW = DataClassRowMapper.newInstance(KnowledgeProcessingTaskPO.class);
    private final JdbcTemplate jdbc;

    public JdbcKnowledgeMappers(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void insertBase(KnowledgeBasePO v) {
        jdbc.update("INSERT INTO kb_knowledge_base (id,tenant_id,code,name,description,knowledge_type,visibility_scope,owner_department_id,status,current_index_release_id,created_by,created_at,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.tenantId(), v.code(), v.name(), v.description(), v.knowledgeType(), v.visibilityScope(), v.ownerDepartmentId(), v.status(), v.currentIndexReleaseId(), v.createdBy(), v.createdAt(), v.updatedBy(), v.updatedAt());
    }

    @Override
    public void updateBase(KnowledgeBasePO v) {
        jdbc.update("UPDATE kb_knowledge_base SET name=?,description=?,knowledge_type=?,status=?,updated_by=?,updated_at=? WHERE id=? AND tenant_id=?",
                v.name(), v.description(), v.knowledgeType(), v.status(), v.updatedBy(), v.updatedAt(), v.id(), v.tenantId());
    }

    @Override public KnowledgeBasePO findBase(String tenantId, String id) {
        return one("SELECT * FROM kb_knowledge_base WHERE tenant_id=? AND id=?", BASE_ROW, tenantId, id);
    }
    @Override public KnowledgeBasePO findBaseByCode(String tenantId, String code) {
        return one("SELECT * FROM kb_knowledge_base WHERE tenant_id=? AND code=?", BASE_ROW, tenantId, code);
    }
    @Override public void lockBase(String id) { jdbc.queryForObject("SELECT id FROM kb_knowledge_base WHERE id=? FOR UPDATE", String.class, id); }
    @Override public List<KnowledgeBasePO> listBases(String tenantId, String keyword, String type, String status, int offset, int limit) {
        Filter filter = baseFilter(tenantId, keyword, type, status);
        filter.args.add(limit); filter.args.add(offset);
        return jdbc.query("SELECT * FROM kb_knowledge_base " + filter.sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?", BASE_ROW, filter.args.toArray());
    }
    @Override public long countBases(String tenantId, String keyword, String type, String status) {
        Filter filter = baseFilter(tenantId, keyword, type, status);
        return jdbc.queryForObject("SELECT COUNT(*) FROM kb_knowledge_base " + filter.sql, Long.class, filter.args.toArray());
    }

    @Override public void insertDirectory(KnowledgeDirectoryPO v) {
        jdbc.update("INSERT INTO kb_directory (id,knowledge_base_id,parent_id,name,path,sort_no,status,created_by,created_at,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.knowledgeBaseId(), v.parentId(), v.name(), v.path(), v.sortNo(), v.status(), v.createdBy(), v.createdAt(), v.updatedBy(), v.updatedAt());
    }
    @Override public void updateDirectory(KnowledgeDirectoryPO v) {
        jdbc.update("UPDATE kb_directory SET name=?,path=?,sort_no=?,status=?,updated_by=?,updated_at=? WHERE id=? AND knowledge_base_id=?",
                v.name(), v.path(), v.sortNo(), v.status(), v.updatedBy(), v.updatedAt(), v.id(), v.knowledgeBaseId());
    }
    @Override public KnowledgeDirectoryPO findDirectory(String baseId, String id) {
        return one("SELECT * FROM kb_directory WHERE knowledge_base_id=? AND id=?", DIRECTORY_ROW, baseId, id);
    }
    @Override public KnowledgeDirectoryPO findDirectoryById(String id) { return one("SELECT * FROM kb_directory WHERE id=?", DIRECTORY_ROW, id); }
    @Override public KnowledgeDirectoryPO findDirectoryByName(String baseId, String parentId, String name) {
        if (parentId == null) {
            return one("SELECT * FROM kb_directory WHERE knowledge_base_id=? AND parent_id IS NULL AND name=?", DIRECTORY_ROW, baseId, name);
        }
        return one("SELECT * FROM kb_directory WHERE knowledge_base_id=? AND parent_id=? AND name=?", DIRECTORY_ROW, baseId, parentId, name);
    }
    @Override public List<KnowledgeDirectoryPO> listDirectories(String baseId) {
        return jdbc.query("SELECT * FROM kb_directory WHERE knowledge_base_id=? ORDER BY path,sort_no,id", DIRECTORY_ROW, baseId);
    }

    @Override public void insertDocument(KnowledgeDocumentPO v) {
        jdbc.update("INSERT INTO kb_document (id,knowledge_base_id,directory_id,title,document_code,source_type,status,current_published_version_id,created_by,created_at,updated_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.knowledgeBaseId(), v.directoryId(), v.title(), v.documentCode(), v.sourceType(), v.status(), v.currentPublishedVersionId(), v.createdBy(), v.createdAt(), v.updatedBy(), v.updatedAt());
    }
    @Override public KnowledgeDocumentPO findDocument(String id) {
        return one("SELECT * FROM kb_document WHERE id=?", DOCUMENT_ROW, id);
    }
    @Override public void lockDocument(String id) { jdbc.queryForObject("SELECT id FROM kb_document WHERE id=? FOR UPDATE", String.class, id); }
    @Override public List<KnowledgeDocumentPO> listDocuments(String baseId, String directoryId, String keyword, String status, int offset, int limit) {
        Filter filter = documentFilter(baseId, directoryId, keyword, status);
        filter.args.add(limit); filter.args.add(offset);
        return jdbc.query("SELECT * FROM kb_document " + filter.sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?", DOCUMENT_ROW, filter.args.toArray());
    }
    @Override public long countDocuments(String baseId, String directoryId, String keyword, String status) {
        Filter filter = documentFilter(baseId, directoryId, keyword, status);
        return jdbc.queryForObject("SELECT COUNT(*) FROM kb_document " + filter.sql, Long.class, filter.args.toArray());
    }
    @Override public boolean hasDocumentContent(String baseId, String sha256) {
        Long count = jdbc.queryForObject("SELECT COUNT(*) FROM kb_document_version v JOIN kb_document d ON d.id=v.document_id WHERE d.knowledge_base_id=? AND v.file_sha256=?", Long.class, baseId, sha256);
        return count != null && count > 0;
    }

    @Override public void insertVersion(KnowledgeDocumentVersionPO v) {
        jdbc.update("INSERT INTO kb_document_version (id,document_id,version_no,file_id,file_sha256,content_type,change_summary,effective_date,status,parse_metadata,error_code,error_message,created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.documentId(), v.versionNo(), v.fileId(), v.fileSha256(), v.contentType(), v.changeSummary(), v.effectiveDate(), v.status(), v.parseMetadata(), v.errorCode(), v.errorMessage(), v.createdBy(), v.createdAt(), v.publishedAt());
    }
    @Override public void updateVersionState(String id, String status, String errorCode, String errorMessage) {
        jdbc.update("UPDATE kb_document_version SET status=?,error_code=?,error_message=? WHERE id=?", status, errorCode, errorMessage, id);
    }
    @Override public KnowledgeDocumentVersionPO findVersion(String id) { return one("SELECT * FROM kb_document_version WHERE id=?", VERSION_ROW, id); }
    @Override public List<KnowledgeDocumentVersionPO> listVersions(String documentId) { return jdbc.query("SELECT * FROM kb_document_version WHERE document_id=? ORDER BY version_no DESC", VERSION_ROW, documentId); }
    @Override public int nextVersionNo(String documentId) { return jdbc.queryForObject("SELECT COALESCE(MAX(version_no),0)+1 FROM kb_document_version WHERE document_id=?", Integer.class, documentId); }

    @Override public void insertBatch(KnowledgeIngestBatchPO v) {
        jdbc.update("INSERT INTO kb_ingest_batch (id,knowledge_base_id,import_mode,total_count,succeeded_count,failed_count,status,created_by,created_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.knowledgeBaseId(), v.importMode(), v.totalCount(), v.succeededCount(), v.failedCount(), v.status(), v.createdBy(), v.createdAt(), v.finishedAt());
    }
    @Override public KnowledgeIngestBatchPO findBatch(String id) { return one("SELECT * FROM kb_ingest_batch WHERE id=?", BATCH_ROW, id); }
    @Override public void finishBatch(String id, int succeeded, int failed, String status) { jdbc.update("UPDATE kb_ingest_batch SET succeeded_count=?,failed_count=?,status=?,finished_at=NOW(6) WHERE id=?", succeeded, failed, status, id); }

    @Override public void insertItem(KnowledgeIngestItemPO v) {
        jdbc.update("INSERT INTO kb_ingest_item (id,batch_id,file_id,document_id,document_version_id,status,error_code,error_message,retry_of_item_id,created_at,updated_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.batchId(), v.fileId(), v.documentId(), v.documentVersionId(), v.status(), v.errorCode(), v.errorMessage(), v.retryOfItemId(), v.createdAt(), v.updatedAt(), v.finishedAt());
    }
    @Override public void updateItem(KnowledgeIngestItemPO v) {
        jdbc.update("UPDATE kb_ingest_item SET file_id=?,document_id=?,document_version_id=?,status=?,error_code=?,error_message=?,retry_of_item_id=?,updated_at=?,finished_at=? WHERE id=?",
                v.fileId(), v.documentId(), v.documentVersionId(), v.status(), v.errorCode(), v.errorMessage(), v.retryOfItemId(), v.updatedAt(), v.finishedAt(), v.id());
    }
    @Override public KnowledgeIngestItemPO findItem(String id) { return one("SELECT * FROM kb_ingest_item WHERE id=?", ITEM_ROW, id); }
    @Override public List<KnowledgeIngestItemPO> listItems(String batchId) { return jdbc.query("SELECT * FROM kb_ingest_item WHERE batch_id=? ORDER BY created_at,id", ITEM_ROW, batchId); }
    @Override public List<KnowledgeIngestItemPO> listItemsByVersion(String versionId) { return jdbc.query("SELECT * FROM kb_ingest_item WHERE document_version_id=? ORDER BY created_at DESC", ITEM_ROW, versionId); }
    @Override public KnowledgeIngestItemPO findLatestItemByVersion(String versionId) { return one("SELECT * FROM kb_ingest_item WHERE document_version_id=? ORDER BY created_at DESC LIMIT 1", ITEM_ROW, versionId); }
    @Override public void refreshBatchSummary(String batchId) {
        jdbc.update("UPDATE kb_ingest_batch b SET succeeded_count=(SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status='SUCCEEDED'), failed_count=(SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status='FAILED'), status=CASE WHEN (SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status IN ('QUEUED','PROCESSING'))>0 THEN 'RUNNING' WHEN (SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status='FAILED')=0 THEN 'SUCCEEDED' WHEN (SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status='SUCCEEDED')=0 THEN 'FAILED' ELSE 'PARTIAL_FAILED' END, finished_at=CASE WHEN (SELECT COUNT(*) FROM kb_ingest_item i WHERE i.batch_id=b.id AND i.status IN ('QUEUED','PROCESSING'))=0 THEN NOW(6) ELSE NULL END WHERE b.id=?", batchId);
    }

    @Override public void insertTask(KnowledgeProcessingTaskPO v) {
        jdbc.update("INSERT INTO kb_processing_task (id,document_version_id,agent_task_id,stage,status,attempt_no,progress_percent,error_code,error_message,started_at,finished_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                v.id(), v.documentVersionId(), v.agentTaskId(), v.stage(), v.status(), v.attemptNo(), v.progressPercent(), v.errorCode(), v.errorMessage(), v.startedAt(), v.finishedAt(), v.createdAt(), v.updatedAt());
    }
    @Override public void updateTask(KnowledgeProcessingTaskPO v) {
        jdbc.update("UPDATE kb_processing_task SET agent_task_id=?,stage=?,status=?,progress_percent=?,error_code=?,error_message=?,started_at=?,finished_at=?,updated_at=? WHERE id=?",
                v.agentTaskId(), v.stage(), v.status(), v.progressPercent(), v.errorCode(), v.errorMessage(), v.startedAt(), v.finishedAt(), v.updatedAt(), v.id());
    }
    @Override public KnowledgeProcessingTaskPO findTask(String id) { return one("SELECT * FROM kb_processing_task WHERE id=?", TASK_ROW, id); }
    @Override public List<KnowledgeProcessingTaskPO> listTasks(String versionId) { return jdbc.query("SELECT * FROM kb_processing_task WHERE document_version_id=? ORDER BY attempt_no DESC", TASK_ROW, versionId); }
    @Override public int nextAttemptNo(String versionId) { return jdbc.queryForObject("SELECT COALESCE(MAX(attempt_no),0)+1 FROM kb_processing_task WHERE document_version_id=?", Integer.class, versionId); }

    private Filter baseFilter(String tenantId, String keyword, String type, String status) {
        Filter filter = new Filter("WHERE tenant_id=?", tenantId);
        if (text(keyword)) { filter.add(" AND (code LIKE ? OR name LIKE ?)", "%" + keyword.strip() + "%", "%" + keyword.strip() + "%"); }
        if (text(type)) { filter.add(" AND knowledge_type=?", type); }
        if (text(status)) { filter.add(" AND status=?", status); }
        return filter;
    }

    private Filter documentFilter(String baseId, String directoryId, String keyword, String status) {
        Filter filter = new Filter("WHERE knowledge_base_id=?", baseId);
        if (text(directoryId)) { filter.add(" AND directory_id=?", directoryId); }
        if (text(keyword)) { filter.add(" AND (title LIKE ? OR document_code LIKE ?)", "%" + keyword.strip() + "%", "%" + keyword.strip() + "%"); }
        if (text(status)) { filter.add(" AND status=?", status); }
        return filter;
    }

    private <T> T one(String sql, DataClassRowMapper<T> mapper, Object... args) {
        try { return jdbc.queryForObject(sql, mapper, args); }
        catch (EmptyResultDataAccessException ignored) { return null; }
    }
    private static boolean text(String value) { return value != null && !value.isBlank(); }

    private static final class Filter {
        private String sql;
        private final List<Object> args = new ArrayList<>();
        private Filter(String sql, Object... initial) { this.sql = sql; args.addAll(List.of(initial)); }
        private void add(String fragment, Object... values) { sql += fragment; args.addAll(List.of(values)); }
    }
}
