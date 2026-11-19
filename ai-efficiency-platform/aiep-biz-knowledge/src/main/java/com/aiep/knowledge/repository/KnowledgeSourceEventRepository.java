package com.aiep.knowledge.repository;

import com.aiep.knowledge.api.KnowledgeSourceEvent;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** 本模块生命周期同事务写入，跨模块只经Facade取refs；未启用不访问新表。 */
@Repository
public class KnowledgeSourceEventRepository {
    private final boolean enabled;private final JdbcTemplate jdbc;
    public KnowledgeSourceEventRepository(@Value("${aiep.knowledge.memory-source-metadata-enabled:false}") boolean enabled,JdbcTemplate jdbc){this.enabled=enabled;this.jdbc=jdbc;}
    public void changed(String base,String reason) {
        if(!enabled)return;
        jdbc.update("INSERT INTO kb_memory_source_outbox(event_id,tenant_id,knowledge_base_id,reason,status) SELECT ?,tenant_id,id,?,'PENDING' FROM kb_knowledge_base WHERE id=?",UUID.randomUUID().toString(),reason,base);
    }
    public List<KnowledgeSourceEvent> pending(int limit) {
        if(!enabled)return List.of();if(limit<1||limit>100)throw new IllegalArgumentException("KB_SOURCE_EVENT_LIMIT_INVALID");
        return jdbc.query("SELECT event_id,tenant_id,knowledge_base_id,reason FROM kb_memory_source_outbox WHERE status='PENDING' ORDER BY created_at,event_id LIMIT ?",(rs,row)->new KnowledgeSourceEvent(rs.getString(1),rs.getString(2),rs.getString(3),rs.getString(4)),limit);
    }
    public void versionChanged(String version) {
        if(!enabled)return;
        jdbc.update("INSERT INTO kb_memory_source_outbox(event_id,tenant_id,knowledge_base_id,reason,status) SELECT ?,b.tenant_id,b.id,'DOCUMENT_STATE_CHANGED','PENDING' FROM kb_document_version v JOIN kb_document d ON d.id=v.document_id JOIN kb_knowledge_base b ON b.id=d.knowledge_base_id WHERE v.id=?",UUID.randomUUID().toString(),version);
    }
    public void acknowledge(String event){if(!enabled)throw new IllegalStateException("KB_SOURCE_EVENTS_DISABLED");jdbc.update("UPDATE kb_memory_source_outbox SET status='DELIVERED' WHERE event_id=? AND status='PENDING'",event);}
}
