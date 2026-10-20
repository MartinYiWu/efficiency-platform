package com.aiep.knowledge.application;

import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeDocumentPO;
import com.aiep.knowledge.repository.KnowledgeDocumentVersionPO;
import com.aiep.knowledge.repository.KnowledgeIngestBatchPO;
import com.aiep.knowledge.repository.KnowledgeIngestItemPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.knowledge.repository.KnowledgeProcessingTaskPO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceIngestRequest;
import com.aiep.platformai.api.dto.CustomerServiceIngestView;
import com.aiep.platformfile.api.FileFacade;
import com.aiep.platformfile.api.FileObjectView;
import java.math.BigInteger;
import java.net.URI;
import java.security.SecureRandom;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

@Service
public class KnowledgeDocumentService {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final char[] CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();
    private final KnowledgeMappers repository;
    private final FileFacade files;
    private final AiInvokeFacade ai;
    private final TransactionTemplate transactions;

    public KnowledgeDocumentService(
            KnowledgeMappers repository,
            FileFacade files,
            AiInvokeFacade ai,
            TransactionTemplate transactions) {
        this.repository = repository;
        this.files = files;
        this.ai = ai;
        this.transactions = transactions;
    }

    public KnowledgeIngestItemPO processNewDocument(
            String baseId,
            String directoryId,
            String itemId,
            MultipartFile upload,
            String sourceType) {
        requireActiveBase(baseId);
        requireActiveDirectory(baseId, directoryId);
        FileObjectView file = files.store(KnowledgeBaseService.TENANT_ID, upload);
        PreparedIngest prepared = transactions.execute(status -> {
            repository.lockBase(baseId);
            if (repository.hasDocumentContent(baseId, file.sha256())) {
                throw new KnowledgeException("KB_DUPLICATE_CONTENT", "知识库中已存在相同内容");
            }
            LocalDateTime now = LocalDateTime.now();
            KnowledgeDocumentPO document = new KnowledgeDocumentPO(
                    UUID.randomUUID().toString(), baseId, emptyToNull(directoryId),
                    title(file.originalName()), nextDocumentCode(), sourceType, "ACTIVE", null,
                    KnowledgeBaseService.USER_ID, now, KnowledgeBaseService.USER_ID, now);
            KnowledgeDocumentVersionPO version = new KnowledgeDocumentVersionPO(
                    UUID.randomUUID().toString(), document.id(), 1, file.id(), file.sha256(),
                    file.contentType(), null, null, "PROCESSING", null, null, null,
                    KnowledgeBaseService.USER_ID, now, null);
            KnowledgeProcessingTaskPO task = task(version.id(), 1, null);
            KnowledgeIngestItemPO item = new KnowledgeIngestItemPO(
                    itemId, requiredItem(itemId).batchId(), file.id(), document.id(), version.id(),
                    "PROCESSING", null, null, requiredItem(itemId).retryOfItemId(),
                    requiredItem(itemId).createdAt(), now, null);
            repository.insertDocument(document);
            repository.insertVersion(version);
            repository.insertTask(task);
            repository.updateItem(item);
            return new PreparedIngest(document, version, task, item, file);
        });
        if (prepared == null) throw new IllegalStateException("知识文档事务未执行");
        return submit(prepared);
    }

    public KnowledgeViews.DocumentVersionView uploadVersion(
            String documentId,
            MultipartFile upload,
            String changeSummary,
            LocalDate effectiveDate) {
        String summary = requireChangeSummary(changeSummary);
        KnowledgeDocumentPO document = requiredDocument(documentId);
        if ("ARCHIVED".equals(document.status())) {
            throw new KnowledgeException("KB_DOCUMENT_ARCHIVED", "归档文档不能创建新版本");
        }
        FileObjectView file = files.store(KnowledgeBaseService.TENANT_ID, upload);
        String batchId = UUID.randomUUID().toString();
        String itemId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now();
        repository.insertBatch(new KnowledgeIngestBatchPO(
                batchId, document.knowledgeBaseId(), "NEW_VERSION", 1, 0, 0,
                "RUNNING", KnowledgeBaseService.USER_ID, now, null));
        repository.insertItem(new KnowledgeIngestItemPO(
                itemId, batchId, null, document.id(), null, "QUEUED", null, null,
                null, now, now, null));
        PreparedIngest prepared = transactions.execute(status -> {
            repository.lockBase(document.knowledgeBaseId());
            repository.lockDocument(document.id());
            if (repository.hasDocumentContent(document.knowledgeBaseId(), file.sha256())) {
                throw new KnowledgeException("KB_DUPLICATE_CONTENT", "知识库中已存在相同内容");
            }
            KnowledgeDocumentVersionPO version = new KnowledgeDocumentVersionPO(
                    UUID.randomUUID().toString(), document.id(), repository.nextVersionNo(document.id()),
                    file.id(), file.sha256(), file.contentType(), summary, effectiveDate,
                    "PROCESSING", null, null, null, KnowledgeBaseService.USER_ID, now, null);
            KnowledgeProcessingTaskPO task = task(version.id(), repository.nextAttemptNo(version.id()), null);
            KnowledgeIngestItemPO item = new KnowledgeIngestItemPO(
                    itemId, batchId, file.id(), document.id(), version.id(), "PROCESSING",
                    null, null, null, now, now, null);
            repository.insertVersion(version);
            repository.insertTask(task);
            repository.updateItem(item);
            return new PreparedIngest(document, version, task, item, file);
        });
        if (prepared == null) throw new IllegalStateException("文档版本事务未执行");
        KnowledgeIngestItemPO submitted = submit(prepared);
        repository.finishBatch(batchId, 1, 0, "RUNNING");
        return versionView(repository.findVersion(submitted.documentVersionId()));
    }

    public KnowledgeIngestItemPO retryFailedItem(KnowledgeIngestItemPO failed, String newItemId) {
        if (!"FAILED".equals(failed.status())) {
            throw new KnowledgeException("KB_RETRY_NOT_ALLOWED", "只有失败项可以重试");
        }
        KnowledgeDocumentVersionPO version = requiredVersion(failed.documentVersionId());
        KnowledgeDocumentPO document = requiredDocument(version.documentId());
        FileObjectView file = files.get(KnowledgeBaseService.TENANT_ID, version.fileId());
        LocalDateTime now = LocalDateTime.now();
        PreparedIngest prepared = transactions.execute(status -> {
            KnowledgeIngestItemPO retry = new KnowledgeIngestItemPO(
                    newItemId, failed.batchId(), file.id(), document.id(), version.id(),
                    "PROCESSING", null, null, failed.id(), now, now, null);
            KnowledgeProcessingTaskPO task = task(
                    version.id(), repository.nextAttemptNo(version.id()), null);
            repository.insertItem(retry);
            repository.insertTask(task);
            return new PreparedIngest(document, version, task, retry, file);
        });
        if (prepared == null) throw new IllegalStateException("重试事务未执行");
        return submit(prepared);
    }

    public KnowledgeViews.PageView<KnowledgeViews.DocumentView> list(
            String baseId, String directoryId, String keyword, String status, int page, int pageSize) {
        requireBase(baseId);
        KnowledgeBaseService.Page pageValue = KnowledgeBaseService.page(page, pageSize);
        List<KnowledgeViews.DocumentView> items = repository.listDocuments(
                        baseId, directoryId, keyword, status, pageValue.offset(), pageValue.pageSize())
                .stream().map(value -> documentView(value, List.of())).toList();
        return new KnowledgeViews.PageView<>(items, pageValue.page(), pageValue.pageSize(),
                repository.countDocuments(baseId, directoryId, keyword, status));
    }

    public KnowledgeViews.DocumentView getDocument(String id) {
        KnowledgeDocumentPO document = requiredDocument(id);
        return documentView(document, repository.listVersions(id).stream().map(this::versionView).toList());
    }

    public KnowledgeViews.DocumentVersionView getVersion(String id) {
        return versionView(requiredVersion(id));
    }

    public KnowledgeViews.ProcessingTaskView getTask(String id) {
        KnowledgeProcessingTaskPO task = repository.findTask(id);
        if (task == null) throw new KnowledgeException("KB_TASK_NOT_FOUND", "处理任务不存在");
        if (task.agentTaskId() != null && !isTerminal(task.status())) {
            CustomerServiceIngestView remote = ai.queryCustomerServiceIngest(task.agentTaskId());
            KnowledgeProcessingTaskPO refreshed = merge(task, remote);
            repository.updateTask(refreshed);
            projectTerminal(refreshed);
            task = refreshed;
        }
        return taskView(task);
    }

    public KnowledgeViews.ProcessingTaskView retryTask(String id) {
        KnowledgeProcessingTaskPO failed = repository.findTask(id);
        if (failed == null) throw new KnowledgeException("KB_TASK_NOT_FOUND", "处理任务不存在");
        if (!"FAILED".equals(failed.status())) {
            throw new KnowledgeException("KB_RETRY_NOT_ALLOWED", "只有失败任务可以重试");
        }
        KnowledgeIngestItemPO failedItem = repository.listItemsByVersion(failed.documentVersionId()).stream()
                .filter(item -> "FAILED".equals(item.status()))
                .findFirst()
                .orElseThrow(() -> new KnowledgeException("KB_RETRY_STATE_INVALID", "失败任务缺少导入项"));
        KnowledgeIngestItemPO retry = retryFailedItem(failedItem, UUID.randomUUID().toString());
        return taskView(repository.listTasks(retry.documentVersionId()).getFirst());
    }

    private KnowledgeIngestItemPO submit(PreparedIngest prepared) {
        URI readUrl = files.createReadUrl(KnowledgeBaseService.TENANT_ID, prepared.file().id(), null);
        try {
            CustomerServiceIngestView accepted = ai.submitCustomerServiceIngest(new CustomerServiceIngestRequest(
                    "customer-service-ingest/1", prepared.task().id(), KnowledgeBaseService.TENANT_ID,
                    prepared.document().knowledgeBaseId(), prepared.document().id(), prepared.version().id(),
                    prepared.document().title(), prepared.version().versionNo(),
                    prepared.file().originalName(), prepared.file().contentType(), prepared.file().sizeBytes(),
                    prepared.file().sha256(), readUrl.toString()));
            LocalDateTime now = LocalDateTime.now();
            KnowledgeProcessingTaskPO updatedTask = new KnowledgeProcessingTaskPO(
                    prepared.task().id(), prepared.version().id(), accepted.taskId(), accepted.stage(),
                    accepted.status(), prepared.task().attemptNo(), accepted.progressPercent(),
                    accepted.errorCode(), accepted.errorMessage(), now, null,
                    prepared.task().createdAt(), now);
            KnowledgeIngestItemPO updatedItem = new KnowledgeIngestItemPO(
                    prepared.item().id(), prepared.item().batchId(), prepared.item().fileId(),
                    prepared.item().documentId(), prepared.item().documentVersionId(), "PROCESSING",
                    null, null, prepared.item().retryOfItemId(), prepared.item().createdAt(), now, null);
            repository.updateTask(updatedTask);
            repository.updateItem(updatedItem);
            return updatedItem;
        } catch (RuntimeException exception) {
            LocalDateTime now = LocalDateTime.now();
            String code = exception instanceof KnowledgeException knowledge ? knowledge.getCode() : "KB_AGENT_SUBMIT_FAILED";
            KnowledgeProcessingTaskPO failedTask = new KnowledgeProcessingTaskPO(
                    prepared.task().id(), prepared.version().id(), null, prepared.task().stage(), "FAILED",
                    prepared.task().attemptNo(), prepared.task().progressPercent(), code,
                    "文档处理任务提交失败", prepared.task().startedAt(), now,
                    prepared.task().createdAt(), now);
            KnowledgeIngestItemPO failedItem = new KnowledgeIngestItemPO(
                    prepared.item().id(), prepared.item().batchId(), prepared.item().fileId(),
                    prepared.item().documentId(), prepared.item().documentVersionId(), "FAILED", code,
                    "文档处理任务提交失败", prepared.item().retryOfItemId(), prepared.item().createdAt(), now, now);
            repository.updateTask(failedTask);
            repository.updateItem(failedItem);
            repository.updateVersionState(prepared.version().id(), "FAILED", code, "文档处理任务提交失败");
            repository.refreshBatchSummary(prepared.item().batchId());
            throw new KnowledgeException(code, "文档处理任务提交失败", exception);
        }
    }

    private KnowledgeIngestItemPO requiredItem(String id) {
        KnowledgeIngestItemPO item = repository.findItem(id);
        if (item == null) throw new KnowledgeException("KB_IMPORT_ITEM_NOT_FOUND", "导入项不存在");
        return item;
    }
    private KnowledgeBasePO requireBase(String id) {
        KnowledgeBasePO value = repository.findBase(KnowledgeBaseService.TENANT_ID, id);
        if (value == null) throw new KnowledgeException("KB_BASE_NOT_FOUND", "知识库不存在");
        return value;
    }
    private void requireActiveBase(String id) {
        if (!"ACTIVE".equals(requireBase(id).status())) throw new KnowledgeException("KB_BASE_NOT_ACTIVE", "知识库未启用");
    }
    private void requireActiveDirectory(String baseId, String id) {
        if (id == null || id.isBlank()) return;
        var value = repository.findDirectory(baseId, id);
        if (value == null) throw new KnowledgeException("KB_DIRECTORY_NOT_FOUND", "目录不存在");
        if (!"ACTIVE".equals(value.status())) throw new KnowledgeException("KB_DIRECTORY_DISABLED", "目录已停用");
    }
    private KnowledgeDocumentPO requiredDocument(String id) {
        KnowledgeDocumentPO value = repository.findDocument(id);
        if (value == null) throw new KnowledgeException("KB_DOCUMENT_NOT_FOUND", "文档不存在");
        return value;
    }
    private KnowledgeDocumentVersionPO requiredVersion(String id) {
        KnowledgeDocumentVersionPO value = repository.findVersion(id);
        if (value == null) throw new KnowledgeException("KB_VERSION_NOT_FOUND", "文档版本不存在");
        return value;
    }
    private KnowledgeProcessingTaskPO task(String versionId, int attempt, String retryStage) {
        LocalDateTime now = LocalDateTime.now();
        return new KnowledgeProcessingTaskPO(
                UUID.randomUUID().toString(), versionId, null,
                retryStage == null ? "PREFLIGHT" : retryStage, "QUEUED", attempt, 0,
                null, null, null, null, now, now);
    }
    private KnowledgeProcessingTaskPO merge(KnowledgeProcessingTaskPO local, CustomerServiceIngestView remote) {
        if (remote.progressPercent() < local.progressPercent()) {
            throw new KnowledgeException("KB_TASK_PROGRESS_REGRESSION", "处理任务进度不可回退");
        }
        if (stageRank(remote.stage()) < stageRank(local.stage())) {
            throw new KnowledgeException("KB_TASK_STAGE_REGRESSION", "处理任务阶段不可回退");
        }
        LocalDateTime now = LocalDateTime.now();
        return new KnowledgeProcessingTaskPO(
                local.id(), local.documentVersionId(), local.agentTaskId(), remote.stage(), remote.status(),
                local.attemptNo(), remote.progressPercent(), remote.errorCode(), remote.errorMessage(),
                local.startedAt() == null ? now : local.startedAt(), isTerminal(remote.status()) ? now : null,
                local.createdAt(), now);
    }
    private void projectTerminal(KnowledgeProcessingTaskPO task) {
        if (!isTerminal(task.status())) return;
        KnowledgeIngestItemPO item = repository.findLatestItemByVersion(task.documentVersionId());
        if (item == null) return;
        LocalDateTime now = LocalDateTime.now();
        boolean succeeded = "SUCCEEDED".equals(task.status());
        repository.updateVersionState(
                task.documentVersionId(), succeeded ? "READY" : "FAILED",
                succeeded ? null : task.errorCode(), succeeded ? null : task.errorMessage());
        repository.updateItem(new KnowledgeIngestItemPO(
                item.id(), item.batchId(), item.fileId(), item.documentId(), item.documentVersionId(),
                succeeded ? "SUCCEEDED" : "FAILED", succeeded ? null : task.errorCode(),
                succeeded ? null : task.errorMessage(), item.retryOfItemId(), item.createdAt(), now, now));
        repository.refreshBatchSummary(item.batchId());
    }
    private static int stageRank(String stage) {
        if (stage == null) return -1;
        return switch (stage) {
            case "PREFLIGHT" -> 0;
            case "PARSE" -> 1;
            case "OCR" -> 2;
            case "CHUNK" -> 3;
            case "EMBED" -> 4;
            case "VERIFY" -> 5;
            default -> throw new KnowledgeException("KB_TASK_STAGE_INVALID", "处理任务阶段无效");
        };
    }
    private KnowledgeViews.DocumentVersionView versionView(KnowledgeDocumentVersionPO v) {
        return new KnowledgeViews.DocumentVersionView(
                v.id(), v.documentId(), v.versionNo(), v.fileId(), v.fileSha256(), v.contentType(),
                v.changeSummary(), v.effectiveDate(), v.status(), v.errorCode(), v.errorMessage(),
                v.createdAt(), repository.listTasks(v.id()).stream().map(KnowledgeDocumentService::taskView).toList());
    }
    private static KnowledgeViews.DocumentView documentView(KnowledgeDocumentPO v, List<KnowledgeViews.DocumentVersionView> versions) {
        return new KnowledgeViews.DocumentView(v.id(), v.knowledgeBaseId(), v.directoryId(), v.title(),
                v.documentCode(), v.sourceType(), v.status(), v.currentPublishedVersionId(), versions);
    }
    private static KnowledgeViews.ProcessingTaskView taskView(KnowledgeProcessingTaskPO v) {
        return new KnowledgeViews.ProcessingTaskView(v.id(), v.documentVersionId(), v.agentTaskId(),
                v.stage(), v.status(), v.attemptNo(), v.progressPercent(), v.errorCode(),
                v.errorMessage(), v.startedAt(), v.finishedAt());
    }
    private static String requireChangeSummary(String value) {
        if (value == null || value.isBlank() || value.strip().length() > 500) {
            throw new KnowledgeException("KB_CHANGE_SUMMARY_REQUIRED", "变更说明长度必须为 1 到 500 个字符");
        }
        return value.strip();
    }
    private static String title(String fileName) {
        int index = fileName.lastIndexOf('.');
        return index <= 0 ? fileName : fileName.substring(0, index);
    }
    private static String emptyToNull(String value) { return value == null || value.isBlank() ? null : value; }
    private static boolean isTerminal(String status) { return List.of("SUCCEEDED", "FAILED", "CANCELLED").contains(status); }

    private static String nextDocumentCode() {
        byte[] bytes = new byte[16];
        long millis = System.currentTimeMillis();
        for (int index = 5; index >= 0; index--) { bytes[index] = (byte) millis; millis >>>= 8; }
        byte[] random = new byte[10]; RANDOM.nextBytes(random); System.arraycopy(random, 0, bytes, 6, 10);
        BigInteger value = new BigInteger(1, bytes);
        char[] encoded = new char[26];
        for (int index = 25; index >= 0; index--) {
            encoded[index] = CROCKFORD[value.and(BigInteger.valueOf(31)).intValue()];
            value = value.shiftRight(5);
        }
        return "DOC-" + new String(encoded);
    }

    private record PreparedIngest(
            KnowledgeDocumentPO document,
            KnowledgeDocumentVersionPO version,
            KnowledgeProcessingTaskPO task,
            KnowledgeIngestItemPO item,
            FileObjectView file) { }
}
