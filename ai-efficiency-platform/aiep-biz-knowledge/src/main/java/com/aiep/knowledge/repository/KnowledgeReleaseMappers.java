package com.aiep.knowledge.repository;

import java.util.List;

public interface KnowledgeReleaseMappers {
    int nextReleaseNo(String knowledgeBaseId);
    void insertRelease(KnowledgeIndexReleasePO value);
    void insertDocuments(List<KnowledgeIndexReleaseDocumentPO> values);
    KnowledgeIndexReleasePO findRelease(String id);
    List<KnowledgeIndexReleasePO> listReleases(String knowledgeBaseId);
    List<KnowledgeIndexReleaseDocumentPO> listDocuments(String releaseId);
    void markFailed(String id);
    void markReady(String id, int documentCount, int chunkCount, String checksum);
    boolean activate(String knowledgeBaseId, String expectedCurrentId, String targetId);
}
