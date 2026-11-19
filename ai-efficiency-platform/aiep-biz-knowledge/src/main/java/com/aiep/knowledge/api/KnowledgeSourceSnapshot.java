package com.aiep.knowledge.api;

import java.time.Instant;
import java.util.List;

/** 当前主体可用的已发布文档目录；仅元数据，不返回正文或把release当全库权限。 */
public record KnowledgeSourceSnapshot(String tenantId,String knowledgeBaseId,String indexReleaseId,
        String releaseChecksum,Instant checkedAt,List<Document> documents) {
    public KnowledgeSourceSnapshot {documents=List.copyOf(documents);}
    public record Document(String documentId,String documentVersionId,String fileSha256) { }
}
