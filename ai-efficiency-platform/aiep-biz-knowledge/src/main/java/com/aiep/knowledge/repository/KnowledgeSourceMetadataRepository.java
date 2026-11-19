package com.aiep.knowledge.repository;

import java.time.LocalDate;
import java.util.List;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** 知识拥有模块一次有界JOIN读取当前发布目录，不把正文/源仓储暴露到AIHub。 */
@Repository
public class KnowledgeSourceMetadataRepository {
    private final JdbcTemplate jdbc;
    public KnowledgeSourceMetadataRepository(JdbcTemplate jdbc){this.jdbc=jdbc;}
    public record Row(String tenantId,String knowledgeBaseId,String visibilityScope,String ownerDepartmentId,String baseStatus,
            String releaseId,String releaseStatus,String releaseChecksum,int documentCount,String documentId,String documentStatus,
            String documentVersionId,String currentPublishedVersionId,String memberSha256,String fileSha256,String versionStatus,LocalDate effectiveDate) { }
    public List<Row> snapshot(String tenant,String base,String release) {
        return jdbc.query("SELECT b.tenant_id,b.id AS knowledge_base_id,b.visibility_scope,b.owner_department_id,b.status AS base_status,"
                +"r.id AS release_id,r.status AS release_status,r.checksum AS release_checksum,r.document_count,m.document_id,d.status AS document_status,"
                +"m.document_version_id,d.current_published_version_id,m.document_sha256 AS member_sha256,v.file_sha256,v.status AS version_status,v.effective_date "
                +"FROM kb_knowledge_base b JOIN kb_index_release r ON r.knowledge_base_id=b.id AND r.id=b.current_index_release_id "
                +"LEFT JOIN kb_index_release_document m ON m.index_release_id=r.id "
                +"LEFT JOIN kb_document d ON d.id=m.document_id AND d.knowledge_base_id=b.id "
                +"LEFT JOIN kb_document_version v ON v.id=m.document_version_id AND v.document_id=d.id "
                +"WHERE CAST(b.tenant_id AS BINARY)=CAST(? AS BINARY) AND b.id=? AND r.id=? ORDER BY m.document_id LIMIT 129 LOCK IN SHARE MODE",
                DataClassRowMapper.newInstance(Row.class),tenant,base,release);
    }
}
