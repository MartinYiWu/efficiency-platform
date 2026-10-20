package com.aiep.knowledge.repository;

import java.util.List;

public interface KnowledgeMappers {
    void insertBase(KnowledgeBasePO value);
    void updateBase(KnowledgeBasePO value);
    KnowledgeBasePO findBase(String tenantId, String id);
    KnowledgeBasePO findBaseByCode(String tenantId, String code);
    void lockBase(String id);
    List<KnowledgeBasePO> listBases(String tenantId, String keyword, String type, String status, int offset, int limit);
    long countBases(String tenantId, String keyword, String type, String status);

    void insertDirectory(KnowledgeDirectoryPO value);
    void updateDirectory(KnowledgeDirectoryPO value);
    KnowledgeDirectoryPO findDirectory(String baseId, String id);
    KnowledgeDirectoryPO findDirectoryById(String id);
    KnowledgeDirectoryPO findDirectoryByName(String baseId, String parentId, String name);
    List<KnowledgeDirectoryPO> listDirectories(String baseId);

    void insertDocument(KnowledgeDocumentPO value);
    KnowledgeDocumentPO findDocument(String id);
    void lockDocument(String id);
    List<KnowledgeDocumentPO> listDocuments(String baseId, String directoryId, String keyword, String status, int offset, int limit);
    long countDocuments(String baseId, String directoryId, String keyword, String status);
    boolean hasDocumentContent(String baseId, String sha256);

    void insertVersion(KnowledgeDocumentVersionPO value);
    void updateVersionState(String id, String status, String errorCode, String errorMessage);
    KnowledgeDocumentVersionPO findVersion(String id);
    List<KnowledgeDocumentVersionPO> listVersions(String documentId);
    int nextVersionNo(String documentId);

    void insertBatch(KnowledgeIngestBatchPO value);
    KnowledgeIngestBatchPO findBatch(String id);
    void finishBatch(String id, int succeeded, int failed, String status);

    void insertItem(KnowledgeIngestItemPO value);
    void updateItem(KnowledgeIngestItemPO value);
    KnowledgeIngestItemPO findItem(String id);
    List<KnowledgeIngestItemPO> listItems(String batchId);
    List<KnowledgeIngestItemPO> listItemsByVersion(String documentVersionId);
    KnowledgeIngestItemPO findLatestItemByVersion(String documentVersionId);
    void refreshBatchSummary(String batchId);

    void insertTask(KnowledgeProcessingTaskPO value);
    void updateTask(KnowledgeProcessingTaskPO value);
    KnowledgeProcessingTaskPO findTask(String id);
    List<KnowledgeProcessingTaskPO> listTasks(String documentVersionId);
    int nextAttemptNo(String documentVersionId);
}
