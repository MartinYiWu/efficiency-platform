package com.aiep.knowledge.application;

import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeIngestBatchPO;
import com.aiep.knowledge.repository.KnowledgeIngestItemPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.platformfile.application.FileStorageException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
@ConditionalOnBean(KnowledgeMappers.class)
public class KnowledgeImportService {
    private static final int MAX_FILES = 50;
    private static final long MAX_BATCH_SIZE = 200L * 1024 * 1024;
    private final KnowledgeMappers repository;
    private final KnowledgeDocumentService documents;

    public KnowledgeImportService(KnowledgeMappers repository, KnowledgeDocumentService documents) {
        this.repository = repository;
        this.documents = documents;
    }

    public KnowledgeViews.IngestBatchView uploadSingle(
            String baseId, String directoryId, MultipartFile file) {
        return ingest(baseId, directoryId, List.of(file), "SINGLE", "UPLOAD");
    }

    public KnowledgeViews.IngestBatchView importFiles(
            String baseId, String directoryId, List<? extends MultipartFile> files) {
        return ingest(baseId, directoryId, files, "BATCH", "BATCH_UPLOAD");
    }

    public KnowledgeViews.IngestBatchView getBatch(String id) {
        KnowledgeIngestBatchPO batch = repository.findBatch(id);
        if (batch == null) throw new KnowledgeException("KB_IMPORT_NOT_FOUND", "导入批次不存在");
        return toView(batch, repository.listItems(id));
    }

    public KnowledgeViews.IngestItemView retryItem(String itemId) {
        KnowledgeIngestItemPO failed = repository.findItem(itemId);
        if (failed == null) throw new KnowledgeException("KB_IMPORT_ITEM_NOT_FOUND", "导入项不存在");
        if (!"FAILED".equals(failed.status())) {
            throw new KnowledgeException("KB_RETRY_NOT_ALLOWED", "只有失败项可以重试");
        }
        return toView(documents.retryFailedItem(failed, UUID.randomUUID().toString()));
    }

    private KnowledgeViews.IngestBatchView ingest(
            String baseId,
            String directoryId,
            List<? extends MultipartFile> files,
            String importMode,
            String sourceType) {
        requireActiveBase(baseId);
        validateBatch(files);
        String batchId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now();
        repository.insertBatch(new KnowledgeIngestBatchPO(
                batchId, baseId, importMode, files.size(), 0, 0, "RUNNING",
                KnowledgeBaseService.USER_ID, now, null));
        int succeeded = 0;
        int failed = 0;
        List<String> itemIds = new ArrayList<>();
        for (MultipartFile file : files) {
            String itemId = UUID.randomUUID().toString();
            itemIds.add(itemId);
            repository.insertItem(new KnowledgeIngestItemPO(
                    itemId, batchId, null, null, null, "QUEUED", null, null,
                    null, now, now, null));
            try {
                documents.processNewDocument(baseId, directoryId, itemId, file, sourceType);
                succeeded++;
            } catch (RuntimeException exception) {
                failed++;
                markFailed(itemId, exception);
            }
        }
        String status = batchStatus(succeeded, failed);
        repository.finishBatch(batchId, succeeded, failed, status);
        KnowledgeIngestBatchPO stored = repository.findBatch(batchId);
        if (stored == null) {
            stored = new KnowledgeIngestBatchPO(
                    batchId, baseId, importMode, files.size(), succeeded, failed, status,
                    KnowledgeBaseService.USER_ID, now, LocalDateTime.now());
        }
        return toView(stored, repository.listItems(batchId));
    }

    private void markFailed(String itemId, RuntimeException failure) {
        KnowledgeIngestItemPO current = repository.findItem(itemId);
        if (current == null) return;
        LocalDateTime now = LocalDateTime.now();
        String code = failure instanceof KnowledgeException value ? value.getCode()
                : failure instanceof FileStorageException value ? value.getErrorCode()
                : "KB_IMPORT_FAILED";
        repository.updateItem(new KnowledgeIngestItemPO(
                current.id(), current.batchId(), current.fileId(), current.documentId(),
                current.documentVersionId(), "FAILED", code, safeMessage(failure),
                current.retryOfItemId(), current.createdAt(), now, now));
    }

    private void requireActiveBase(String baseId) {
        KnowledgeBasePO base = repository.findBase(KnowledgeBaseService.TENANT_ID, baseId);
        if (base == null) throw new KnowledgeException("KB_BASE_NOT_FOUND", "知识库不存在");
        if (!"ACTIVE".equals(base.status())) throw new KnowledgeException("KB_BASE_NOT_ACTIVE", "知识库未启用");
    }

    private static void validateBatch(List<? extends MultipartFile> files) {
        if (files == null || files.isEmpty() || files.size() > MAX_FILES) {
            throw new KnowledgeException("KB_BATCH_SIZE_INVALID", "每批文件数必须为 1 到 50");
        }
        long total = 0;
        for (MultipartFile file : files) {
            if (file != null) total += Math.max(file.getSize(), 0);
            if (total > MAX_BATCH_SIZE) {
                throw new KnowledgeException("KB_BATCH_BYTES_EXCEEDED", "批量文件总大小不能超过 200 MiB");
            }
        }
    }

    private static String batchStatus(int succeeded, int failed) {
        if (failed == 0) return "RUNNING";
        if (succeeded == 0) return "FAILED";
        return "PARTIAL_FAILED";
    }
    private static String safeMessage(RuntimeException failure) {
        return failure instanceof KnowledgeException || failure instanceof FileStorageException
                ? failure.getMessage() : "文件导入失败";
    }
    private static KnowledgeViews.IngestBatchView toView(KnowledgeIngestBatchPO batch, List<KnowledgeIngestItemPO> items) {
        return new KnowledgeViews.IngestBatchView(
                batch.id(), batch.knowledgeBaseId(), batch.importMode(), batch.totalCount(),
                batch.succeededCount(), batch.failedCount(), batch.status(), batch.createdAt(),
                batch.finishedAt(), items.stream().map(KnowledgeImportService::toView).toList());
    }
    static KnowledgeViews.IngestItemView toView(KnowledgeIngestItemPO item) {
        return new KnowledgeViews.IngestItemView(
                item.id(), item.batchId(), item.fileId(), item.documentId(),
                item.documentVersionId(), item.status(), item.errorCode(), item.errorMessage(),
                item.retryOfItemId());
    }
}
