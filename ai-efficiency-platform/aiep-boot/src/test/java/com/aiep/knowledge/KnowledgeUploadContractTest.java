package com.aiep.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.application.KnowledgeException;
import com.aiep.knowledge.application.KnowledgeImportService;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.knowledge.repository.KnowledgeIngestBatchPO;
import com.aiep.knowledge.repository.KnowledgeIngestItemPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.knowledge.web.KnowledgeBaseController;
import com.aiep.knowledge.web.KnowledgeDocumentController;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;

class KnowledgeUploadContractTest {

    @Test
    void publicRequestsCannotOverrideDevelopmentIdentity() {
        Set<String> fields = List.of(
                        KnowledgeBaseController.CreateBaseRequest.class,
                        KnowledgeBaseController.UpdateBaseRequest.class,
                        KnowledgeDocumentController.NewVersionRequest.class)
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

    private static MockMultipartFile textFile(String name, String content) {
        return new MockMultipartFile("files", name, "text/plain", content.getBytes(StandardCharsets.UTF_8));
    }
}
