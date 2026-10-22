package com.aiep.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.application.KnowledgeException;
import com.aiep.knowledge.application.KnowledgeViews;
import com.aiep.knowledge.repository.*;
import com.aiep.knowledge.web.KnowledgeDocumentController;
import com.aiep.platformai.api.dto.CustomerServiceIngestRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class KnowledgeEvidenceModeTest {
    @Test
    void policyAndProcessRejectExtractionBeforeStoringFile() throws Exception {
        for (String kind : new String[]{"COMPANY_POLICY", "BUSINESS_PROCESS"}) {
            var repository = mock(KnowledgeMappers.class);
            var files = mock(com.aiep.platformfile.api.FileFacade.class);
            when(repository.findBase("dev", "base-1")).thenReturn(new KnowledgeBasePO(
                    "base-1", "dev", "BASE", "知识库", null, kind, "COMPANY_WIDE", null,
                    "ACTIVE", null, "1", KnowledgeFixtures.NOW, "1", KnowledgeFixtures.NOW));
            var service = new KnowledgeDocumentService(repository, files,
                    mock(com.aiep.platformai.api.AiInvokeFacade.class),
                    mock(org.springframework.transaction.support.TransactionTemplate.class));
            assertThatThrownBy(() -> service.processNewDocument("base-1", null, "item", null,
                    "UPLOAD", "EXTRACTIVE_NARRATIVE"))
                    .isInstanceOf(KnowledgeException.class).extracting("code")
                    .isEqualTo("KB_EVIDENCE_MODE_NOT_ALLOWED");
            verifyNoInteractions(files);
        }
    }

    @Test
    void productAndTechnicalModesPersistAndReachAgent() throws Exception {
        for (String kind : new String[]{"PRODUCT_DOCUMENTATION", "TECHNICAL_DOCUMENTATION"}) {
            var repository = mock(KnowledgeMappers.class);
            var files = mock(com.aiep.platformfile.api.FileFacade.class);
            var ai = mock(com.aiep.platformai.api.AiInvokeFacade.class);
            var tx = mock(org.springframework.transaction.support.TransactionTemplate.class);
            var stored = new java.util.concurrent.atomic.AtomicReference<KnowledgeDocumentVersionPO>();
            doAnswer(i -> { stored.set(i.getArgument(0)); return null; }).when(repository).insertVersion(any());
            when(repository.findVersion(anyString())).thenAnswer(i -> stored.get());
            when(tx.execute(any())).thenAnswer(i -> ((org.springframework.transaction.support.TransactionCallback<?>) i.getArgument(0))
                    .doInTransaction(mock(org.springframework.transaction.TransactionStatus.class)));
            when(repository.findBase("dev", "base-1")).thenReturn(new KnowledgeBasePO(
                    "base-1", "dev", "BASE", "知识库", null, kind, "COMPANY_WIDE", null,
                    "ACTIVE", null, "1", KnowledgeFixtures.NOW, "1", KnowledgeFixtures.NOW));
            when(repository.findItem("item")).thenReturn(KnowledgeFixtures.item("item", "QUEUED", null));
            when(files.store(eq("dev"), any())).thenReturn(new com.aiep.platformfile.api.FileObjectView(
                    "file", "dev", "a.txt", "text/plain", 1, "a".repeat(64), "READY", KnowledgeFixtures.NOW));
            when(files.createReadUrl(eq("dev"), eq("file"), isNull())).thenReturn(java.net.URI.create("https://files.example.test/a"));
            when(ai.submitCustomerServiceIngest(any())).thenReturn(new com.aiep.platformai.api.dto.CustomerServiceIngestView(
                    "customer-service-ingest-view/1", "task", "QUEUED", "PREFLIGHT", 0, null, null));
            new KnowledgeDocumentService(repository, files, ai, tx).processNewDocument(
                    "base-1", null, "item", null, "UPLOAD", "EXTRACTIVE_NARRATIVE");
            var version = org.mockito.ArgumentCaptor.forClass(KnowledgeDocumentVersionPO.class);
            verify(repository).insertVersion(version.capture());
            assertThat(version.getValue().evidenceMode()).isEqualTo("EXTRACTIVE_NARRATIVE");
            var request = org.mockito.ArgumentCaptor.forClass(CustomerServiceIngestRequest.class);
            verify(ai).submitCustomerServiceIngest(request.capture());
            assertThat(new ObjectMapper().valueToTree(request.getValue()).path("evidence_mode").asText()).isEqualTo("EXTRACTIVE_NARRATIVE");
            var publishedDocument = new KnowledgeDocumentPO("doc", "base-1", null, "标题", "DOC-1",
                    "UPLOAD", "ACTIVE", "published-version", "1", KnowledgeFixtures.NOW, "1", KnowledgeFixtures.NOW);
            when(repository.findDocument("doc")).thenReturn(publishedDocument);
            when(repository.nextVersionNo("doc")).thenReturn(2);
            clearInvocations(repository, ai);
            var result = new KnowledgeDocumentService(repository, files, ai, tx).uploadVersion(
                    "doc", null, "更新产品说明", null, "EXTRACTIVE_NARRATIVE");
            assertThat(result.versionNo()).isEqualTo(2);
            assertThat(result.evidenceMode()).isEqualTo("EXTRACTIVE_NARRATIVE");
            assertThat(stored.get().id()).isNotEqualTo("published-version");
            assertThat(publishedDocument.currentPublishedVersionId()).isEqualTo("published-version");
            verify(ai).submitCustomerServiceIngest(request.capture());
            assertThat(request.getValue().evidenceMode()).isEqualTo("EXTRACTIVE_NARRATIVE");
        }
    }
    @Test
    void creationAndReadContractsExposeFrozenMode() {
        for (Class<?> type : new Class<?>[]{KnowledgeDocumentVersionPO.class,
                KnowledgeViews.DocumentVersionView.class, KnowledgeDocumentController.NewVersionRequest.class}) {
            assertThat(Arrays.stream(type.getRecordComponents()).map(c -> c.getName()))
                    .contains("evidenceMode");
        }
    }

    @Test
    void oldIngestConstructorSerializesFullOnly() throws Exception {
        var request = new CustomerServiceIngestRequest("customer-service-ingest/1", "task", "dev",
                "base", "doc", "version", "标题", 1, "file.txt", "text/plain", 1,
                "a".repeat(64), "https://files.example.test/document");
        assertThat(new ObjectMapper().valueToTree(request).path("evidence_mode").asText()).isEqualTo("FULL_ONLY");
    }

    @Test
    void legacyNullModeReadsAsFullOnly() {
        var version = new KnowledgeDocumentVersionPO("version", "doc", 1, "file", "a".repeat(64),
                "text/plain", null, null, "PUBLISHED", null, null, null, "1", KnowledgeFixtures.NOW, KnowledgeFixtures.NOW, null);
        var repository = mock(KnowledgeMappers.class);
        when(repository.findVersion("version")).thenReturn(version);
        when(repository.listTasks("version")).thenReturn(java.util.List.of());
        var service = new KnowledgeDocumentService(repository, mock(com.aiep.platformfile.api.FileFacade.class),
                mock(com.aiep.platformai.api.AiInvokeFacade.class), mock(org.springframework.transaction.support.TransactionTemplate.class));
        assertThat(service.getVersion("version").evidenceMode()).isEqualTo("FULL_ONLY");
        verify(repository, never()).insertVersion(any());
        verify(repository, never()).updateVersionState(anyString(), anyString(), any(), any());
    }
}
