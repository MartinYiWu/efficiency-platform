package com.aiep.knowledge.repository;

import java.util.List;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcKnowledgeReleaseMappers implements KnowledgeReleaseMappers {
    private static final DataClassRowMapper<KnowledgeIndexReleasePO> RELEASE_ROW =
            DataClassRowMapper.newInstance(KnowledgeIndexReleasePO.class);
    private static final DataClassRowMapper<KnowledgeIndexReleaseDocumentPO> DOCUMENT_ROW =
            DataClassRowMapper.newInstance(KnowledgeIndexReleaseDocumentPO.class);
    private final JdbcTemplate jdbc;

    public JdbcKnowledgeReleaseMappers(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public int nextReleaseNo(String knowledgeBaseId) {
        return jdbc.queryForObject(
                "SELECT COALESCE(MAX(release_no),0)+1 FROM kb_index_release WHERE knowledge_base_id=?",
                Integer.class, knowledgeBaseId);
    }

    @Override
    public void insertRelease(KnowledgeIndexReleasePO value) {
        jdbc.update("INSERT INTO kb_index_release "
                        + "(id,knowledge_base_id,release_no,status,document_count,chunk_count,"
                        + "embedding_model,embedding_dimension,checksum,previous_release_id,"
                        + "created_by,created_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                value.id(), value.knowledgeBaseId(), value.releaseNo(), value.status(),
                value.documentCount(), value.chunkCount(), value.embeddingModel(),
                value.embeddingDimension(), value.checksum(), value.previousReleaseId(),
                value.createdBy(), value.createdAt(), value.publishedAt());
    }

    @Override
    public void insertDocuments(List<KnowledgeIndexReleaseDocumentPO> values) {
        jdbc.batchUpdate("INSERT INTO kb_index_release_document "
                        + "(index_release_id,document_id,document_version_id,document_sha256,created_at) "
                        + "VALUES (?,?,?,?,?)",
                values, values.size(), (statement, value) -> {
                    statement.setString(1, value.indexReleaseId());
                    statement.setString(2, value.documentId());
                    statement.setString(3, value.documentVersionId());
                    statement.setString(4, value.documentSha256());
                    statement.setObject(5, value.createdAt());
                });
    }

    @Override
    public KnowledgeIndexReleasePO findRelease(String id) {
        try {
            return jdbc.queryForObject(
                    "SELECT * FROM kb_index_release WHERE id=?", RELEASE_ROW, id);
        } catch (EmptyResultDataAccessException ignored) {
            return null;
        }
    }

    @Override
    public List<KnowledgeIndexReleasePO> listReleases(String knowledgeBaseId) {
        return jdbc.query(
                "SELECT * FROM kb_index_release WHERE knowledge_base_id=? ORDER BY release_no DESC",
                RELEASE_ROW, knowledgeBaseId);
    }

    @Override
    public List<KnowledgeIndexReleaseDocumentPO> listDocuments(String releaseId) {
        return jdbc.query(
                "SELECT * FROM kb_index_release_document WHERE index_release_id=? ORDER BY document_id",
                DOCUMENT_ROW, releaseId);
    }

    @Override
    public void markFailed(String id) {
        jdbc.update("UPDATE kb_index_release SET status='FAILED' WHERE id=? AND status IN ('BUILDING','READY')", id);
    }

    @Override
    public void markReady(String id, int documentCount, int chunkCount, String checksum) {
        int updated = jdbc.update("UPDATE kb_index_release SET status='READY',document_count=?,"
                        + "chunk_count=?,checksum=? WHERE id=? AND status='BUILDING'",
                documentCount, chunkCount, checksum, id);
        if (updated != 1) {
            throw new IllegalStateException("候选索引状态已变化");
        }
    }

    @Override
    public boolean activate(String knowledgeBaseId, String expectedCurrentId, String targetId) {
        int switched;
        if (expectedCurrentId == null) {
            switched = jdbc.update("UPDATE kb_knowledge_base SET current_index_release_id=?,"
                            + "updated_by='1',updated_at=NOW(6) WHERE id=? AND tenant_id='dev' "
                            + "AND current_index_release_id IS NULL",
                    targetId, knowledgeBaseId);
        } else {
            switched = jdbc.update("UPDATE kb_knowledge_base SET current_index_release_id=?,"
                            + "updated_by='1',updated_at=NOW(6) WHERE id=? AND tenant_id='dev' "
                            + "AND current_index_release_id=?",
                    targetId, knowledgeBaseId, expectedCurrentId);
        }
        if (switched != 1) {
            return false;
        }
        if (expectedCurrentId != null) {
            jdbc.update("UPDATE kb_index_release SET status='RETIRED' WHERE id=? AND status='PUBLISHED'",
                    expectedCurrentId);
        }
        jdbc.update("UPDATE kb_index_release SET status='PUBLISHED',published_at=NOW(6) WHERE id=?",
                targetId);
        jdbc.update("UPDATE kb_document_version v JOIN kb_document d ON d.id=v.document_id "
                        + "SET v.status='RETIRED' WHERE d.knowledge_base_id=? AND v.status='PUBLISHED'",
                knowledgeBaseId);
        jdbc.update("UPDATE kb_document_version v JOIN kb_index_release_document m "
                        + "ON m.document_version_id=v.id SET v.status='PUBLISHED',"
                        + "v.published_at=COALESCE(v.published_at,NOW(6)) WHERE m.index_release_id=?",
                targetId);
        jdbc.update("UPDATE kb_document d JOIN kb_index_release_document m ON m.document_id=d.id "
                        + "SET d.current_published_version_id=m.document_version_id,"
                        + "d.updated_by='1',d.updated_at=NOW(6) WHERE m.index_release_id=?",
                targetId);
        return true;
    }
}
