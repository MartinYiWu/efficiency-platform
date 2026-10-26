package com.aiep.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.application.KnowledgeException;
import com.aiep.knowledge.application.KnowledgeImportService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.knowledge.repository.KnowledgeDocumentPO;
import com.aiep.knowledge.repository.KnowledgeDocumentVersionPO;
import com.aiep.knowledge.repository.KnowledgeIngestBatchPO;
import com.aiep.knowledge.repository.KnowledgeIngestItemPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.knowledge.web.KnowledgeBaseController;
import com.aiep.knowledge.web.KnowledgeDocumentController;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceIngestView;
import com.aiep.platformfile.api.FileFacade;
import com.aiep.platformfile.api.FileObjectView;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

class KnowledgeUploadContractTest {

    @Test
    void publicRequestsCannotOverrideDevelopmentIdentity() {
        Set<String> fields = List.of(
                        KnowledgeBaseController.CreateBaseRequest.class,
                        KnowledgeBaseController.UpdateBaseRequest.class,
                        KnowledgeDocumentController.NewVersionRequest.class,
                        KnowledgeDocumentController.ReindexRequest.class)
                .stream()
                .flatMap(type -> List.of(type.getRecordComponents()).stream())
                .map(component -> component.getName().toLowerCase())
                .collect(Collectors.toSet());

        assertThat(fields).doesNotContain("tenantid", "userid", "role", "createdby", "updatedby");
    }

    @Test
    void batchKeepsSuccessfulFileWhenAnotherFileFails() {
        KnowledgeMappers repository = mock(KnowledgeMappers.class);
        KnowledgeDocumentService documents = mock(KnowledgeDocumentService.class);
        when(repository.findBase("dev", "base-1")).thenReturn(KnowledgeFixtures.activeBase());
        when(repository.findBatch(anyString())).thenAnswer(invocation -> {
            KnowledgeIngestBatchPO batch = new KnowledgeIngestBatchPO(
                    invocation.getArgument(0), "base-1", "BATCH", 2, 1, 1,
                    "PARTIAL_FAILED", "1", KnowledgeFixtures.NOW, KnowledgeFixtures.NOW);
            return batch;
        });
        when(repository.listItems(anyString())).thenReturn(List.of(
                KnowledgeFixtures.item("item-1", "SUCCEEDED", null),
                KnowledgeFixtures.item("item-2", "FAILED", "FILE_TYPE_INVALID")));
        when(documents.processNewDocument(anyString(), nullable(String.class), anyString(), any(), anyString()))
                .thenReturn(KnowledgeFixtures.item("item-1", "SUCCEEDED", null))
                .thenThrow(new KnowledgeException("FILE_TYPE_INVALID", "文件类型无效"));
        KnowledgeImportService service = new KnowledgeImportService(repository, documents);
        List<MockMultipartFile> files = List.of(
                textFile("one.txt", "one"),
                textFile("two.exe", "two"));

        KnowledgeViews.IngestBatchView result = service.importFiles("base-1", null, files);

        assertThat(result.status()).isEqualTo("PARTIAL_FAILED");
        assertThat(result.succeededCount()).isEqualTo(1);
        assertThat(result.failedCount()).isEqualTo(1);
        verify(repository).finishBatch(anyString(), org.mockito.ArgumentMatchers.eq(1),
                org.mockito.ArgumentMatchers.eq(1), org.mockito.ArgumentMatchers.eq("PARTIAL_FAILED"));
    }

    @Test
    void newVersionRequiresMeaningfulChangeSummary() {
        KnowledgeDocumentService service = KnowledgeFixtures.documentService();

        assertThatThrownBy(() -> service.uploadVersion(
                "document-1", textFile("v2.txt", "updated"), " ", null))
                .isInstanceOf(KnowledgeException.class)
                .extracting("code")
                .isEqualTo("KB_CHANGE_SUMMARY_REQUIRED");
    }

    @Test
    void retryCreatesNewItemAndAttemptWithoutOverwritingFailure() {
        KnowledgeMappers repository = mock(KnowledgeMappers.class);
        KnowledgeDocumentService documents = mock(KnowledgeDocumentService.class);
        KnowledgeIngestItemPO failed = KnowledgeFixtures.item("failed-1", "FAILED", "PARSE_FAILED");
        when(repository.findItem("failed-1")).thenReturn(failed);
        when(documents.retryFailedItem(eq(failed), anyString()))
                .thenReturn(KnowledgeFixtures.item("retry-1", "QUEUED", null, "failed-1"));
        KnowledgeImportService service = new KnowledgeImportService(repository, documents);

        KnowledgeViews.IngestItemView retried = service.retryItem("failed-1");

        assertThat(retried.id()).isEqualTo("retry-1");
        assertThat(retried.retryOfItemId()).isEqualTo("failed-1");
        assertThat(failed.status()).isEqualTo("FAILED");
    }

    @Test
    void reindexCreatesTechnicalVersionFromPublishedFileWithoutUploadingDuplicate() {
        KnowledgeMappers repository = mock(KnowledgeMappers.class);
        FileFacade files = mock(FileFacade.class);
        AiInvokeFacade ai = mock(AiInvokeFacade.class);
        TransactionTemplate transactions = mock(TransactionTemplate.class);
        AtomicReference<KnowledgeDocumentVersionPO> inserted = new AtomicReference<>();
        KnowledgeDocumentPO document = new KnowledgeDocumentPO(
                "document-1", "base-1", null, "阿里多Agent", "DOC-1", "UPLOAD",
                "ACTIVE", "version-1", "1", KnowledgeFixtures.NOW, "1", KnowledgeFixtures.NOW);
        KnowledgeDocumentVersionPO published = new KnowledgeDocumentVersionPO(
                "version-1", "document-1", 1, "file-1", "a".repeat(64),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "首版", LocalDate.of(2026, 10, 20), "PUBLISHED", null, null, null,
                "1", KnowledgeFixtures.NOW, KnowledgeFixtures.NOW, "FULL_ONLY");
        FileObjectView file = new FileObjectView(
                "file-1", "dev", "阿里多Agent.docx", published.contentType(), 1024,
                published.fileSha256(), "ACTIVE", KnowledgeFixtures.NOW);
        when(repository.findDocument("document-1")).thenReturn(document);
        when(repository.findVersion(anyString())).thenAnswer(invocation ->
                "version-1".equals(invocation.getArgument(0)) ? published : inserted.get());
        when(repository.nextVersionNo("document-1")).thenReturn(2);
        when(repository.nextAttemptNo(anyString())).thenReturn(1);
        when(repository.listTasks(anyString())).thenReturn(List.of());
        doAnswer(invocation -> {
            inserted.set(invocation.getArgument(0));
            return null;
        }).when(repository).insertVersion(any());
        when(files.get("dev", "file-1")).thenReturn(file);
        when(files.createReadUrl(eq("dev"), eq("file-1"), nullable(java.time.Duration.class)))
                .thenReturn(URI.create("https://example.invalid/source.docx"));
        when(ai.submitCustomerServiceIngest(any())).thenReturn(new CustomerServiceIngestView(
                "customer-service-ingest-view/1", "agent-task-1", "RUNNING", "PREFLIGHT",
                0, null, null));
        when(transactions.execute(any())).thenAnswer(invocation -> {
            TransactionCallback<?> callback = invocation.getArgument(0);
            return callback.doInTransaction(mock(TransactionStatus.class));
        });
        KnowledgeDocumentService service = new KnowledgeDocumentService(repository, files, ai, transactions);

        KnowledgeViews.DocumentVersionView result = service.reindex(
                "document-1", "按新版父子切片策略重建索引");

        assertThat(result.versionNo()).isEqualTo(2);
        assertThat(result.fileId()).isEqualTo("file-1");
        assertThat(result.fileSha256()).isEqualTo(published.fileSha256());
        assertThat(result.changeSummary()).isEqualTo("按新版父子切片策略重建索引");
        verify(files, org.mockito.Mockito.never()).store(anyString(), any());
        verify(ai).submitCustomerServiceIngest(any());
    }

    private static MockMultipartFile textFile(String name, String content) {
        return new MockMultipartFile("files", name, "text/plain", content.getBytes(StandardCharsets.UTF_8));
    }
}
