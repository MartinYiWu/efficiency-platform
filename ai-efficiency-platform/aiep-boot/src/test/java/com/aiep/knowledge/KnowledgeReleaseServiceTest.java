package com.aiep.knowledge;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.knowledge.application.KnowledgeException;
import com.aiep.knowledge.application.KnowledgeReleaseService;
import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeDocumentPO;
import com.aiep.knowledge.repository.KnowledgeDocumentVersionPO;
import com.aiep.knowledge.repository.KnowledgeIndexReleaseDocumentPO;
import com.aiep.knowledge.repository.KnowledgeIndexReleasePO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.knowledge.repository.KnowledgeReleaseMappers;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyView;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyRequest;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

class KnowledgeReleaseServiceTest {
    private final KnowledgeMappers knowledge = mock(KnowledgeMappers.class);
    private final AiInvokeFacade ai = mock(AiInvokeFacade.class);
    private final TransactionTemplate transactions = mock(TransactionTemplate.class);
    private final MemoryReleaseMappers releases = new MemoryReleaseMappers();

    @BeforeEach
    void executeTransactionCallbacks() {
        when(transactions.execute(any())).thenAnswer(invocation -> {
            TransactionCallback<?> callback = invocation.getArgument(0);
            return callback.doInTransaction(mock(TransactionStatus.class));
        });
    }

    @Test
    void publishBuildsFullSnapshotAndAtomicallyActivatesAfterVerification() {
        arrangeReadyVersion(null);
        when(ai.verifyCustomerServiceIndex(any())).thenAnswer(invocation -> {
            CustomerServiceIndexVerifyRequest request = invocation.getArgument(0);
            return verified(request.releaseId(), 1, 7, "b".repeat(64));
        });
        KnowledgeReleaseService service = service();

        var result = service.publishVersion("version-2");

        assertThat(result.status()).isEqualTo("PUBLISHED");
        assertThat(result.documentCount()).isEqualTo(1);
        assertThat(result.chunkCount()).isEqualTo(7);
        assertThat(releases.members.get(result.id()))
                .extracting(KnowledgeIndexReleaseDocumentPO::documentVersionId)
                .containsExactly("version-2");
        assertThat(releases.currentReleaseId).isEqualTo(result.id());
    }

    @Test
    void failedAgentVerificationDoesNotChangePublishedPointer() {
        arrangeReadyVersion("release-1");
        releases.addPublished("release-1", "version-1");
        when(ai.verifyCustomerServiceIndex(any())).thenAnswer(invocation -> {
            CustomerServiceIndexVerifyRequest request = invocation.getArgument(0);
            return new CustomerServiceIndexVerifyView(
                    "customer-service-index-verify-view/1", request.releaseId(),
                    "FAILED", 0, 0, null, "KB_INDEX_VERIFY_FAILED", "候选索引验证失败");
        });
        KnowledgeReleaseService service = service();

        assertThatThrownBy(() -> service.publishVersion("version-2"))
                .isInstanceOf(KnowledgeException.class)
                .extracting("code")
                .isEqualTo("KB_INDEX_VERIFY_FAILED");

        assertThat(releases.currentReleaseId).isEqualTo("release-1");
        assertThat(releases.values.values())
                .extracting(KnowledgeIndexReleasePO::status)
                .contains("FAILED", "PUBLISHED");
    }

    @Test
    void concurrentPointerChangePreventsActivation() {
        arrangeReadyVersion("release-1");
        releases.addPublished("release-1", "version-1");
        when(ai.verifyCustomerServiceIndex(any())).thenAnswer(invocation -> {
            CustomerServiceIndexVerifyRequest request = invocation.getArgument(0);
            releases.currentReleaseId = "release-other";
            when(knowledge.findBase("dev", "base-1"))
                    .thenReturn(base("release-other"));
            return verified(request.releaseId(), 1, 2, "c".repeat(64));
        });

        assertThatThrownBy(() -> service().publishVersion("version-2"))
                .isInstanceOf(KnowledgeException.class)
                .extracting("code")
                .isEqualTo("KB_RELEASE_CONFLICT");
        assertThat(releases.currentReleaseId).isEqualTo("release-other");
    }

    @Test
    void rollbackActivatesHistoricalSnapshotWithoutReembedding() {
        arrangeReadyVersion("release-2");
        releases.addPublished("release-2", "version-2");
        releases.addRetired("release-1", "version-1");
        when(knowledge.findBase("dev", "base-1")).thenReturn(base("release-2"));

        var result = service().rollback("release-1");

        assertThat(result.status()).isEqualTo("PUBLISHED");
        assertThat(releases.currentReleaseId).isEqualTo("release-1");
        verify(ai, never()).verifyCustomerServiceIndex(any());
    }

    private KnowledgeReleaseService service() {
        return new KnowledgeReleaseService(knowledge, releases, ai, transactions);
    }

    private void arrangeReadyVersion(String currentReleaseId) {
        when(knowledge.findVersion("version-2")).thenReturn(version("version-2", 2));
        when(knowledge.findDocument("document-1")).thenReturn(document("version-1"));
        when(knowledge.findBase("dev", "base-1")).thenReturn(base(currentReleaseId));
    }

    private static KnowledgeBasePO base(String releaseId) {
        return new KnowledgeBasePO(
                "base-1", "dev", "POLICY", "公司制度", null, "COMPANY_POLICY",
                "COMPANY_WIDE", null, "ACTIVE", releaseId, "1",
                KnowledgeFixtures.NOW, "1", KnowledgeFixtures.NOW);
    }

    private static KnowledgeDocumentPO document(String publishedVersion) {
        return new KnowledgeDocumentPO(
                "document-1", "base-1", null, "制度", "DOC-1", "UPLOAD",
                "ACTIVE", publishedVersion, "1", KnowledgeFixtures.NOW,
                "1", KnowledgeFixtures.NOW);
    }

    private static KnowledgeDocumentVersionPO version(String id, int number) {
        return new KnowledgeDocumentVersionPO(
                id, "document-1", number, "file-2", "a".repeat(64), "text/plain",
                "更新", null, "READY", null, null, null, "1",
                KnowledgeFixtures.NOW, null);
    }

    private static CustomerServiceIndexVerifyView verified(
            String releaseId, int documents, int chunks, String checksum) {
        return new CustomerServiceIndexVerifyView(
                "customer-service-index-verify-view/1", releaseId, "READY",
                documents, chunks, checksum, null, null);
    }

    private static final class MemoryReleaseMappers implements KnowledgeReleaseMappers {
        private final Map<String, KnowledgeIndexReleasePO> values = new HashMap<>();
        private final Map<String, List<KnowledgeIndexReleaseDocumentPO>> members = new HashMap<>();
        private String currentReleaseId;

        @Override public int nextReleaseNo(String baseId) { return values.size() + 1; }
        @Override public void insertRelease(KnowledgeIndexReleasePO value) { values.put(value.id(), value); }
        @Override public void insertDocuments(List<KnowledgeIndexReleaseDocumentPO> value) {
            members.put(value.getFirst().indexReleaseId(), new ArrayList<>(value));
        }
        @Override public KnowledgeIndexReleasePO findRelease(String id) { return values.get(id); }
        @Override public List<KnowledgeIndexReleasePO> listReleases(String baseId) {
            return values.values().stream().filter(v -> v.knowledgeBaseId().equals(baseId)).toList();
        }
        @Override public List<KnowledgeIndexReleaseDocumentPO> listDocuments(String releaseId) {
            return members.getOrDefault(releaseId, List.of());
        }
        @Override public void markFailed(String id) { values.computeIfPresent(id, (key, value) -> value.withStatus("FAILED")); }
        @Override public void markReady(String id, int documents, int chunks, String checksum) {
            values.computeIfPresent(id, (key, value) -> value.ready(documents, chunks, checksum));
        }
        @Override public boolean activate(String baseId, String expectedCurrentId, String targetId) {
            if (!java.util.Objects.equals(currentReleaseId, expectedCurrentId)) return false;
            if (currentReleaseId != null && values.containsKey(currentReleaseId)) {
                values.computeIfPresent(currentReleaseId, (key, value) -> value.withStatus("RETIRED"));
            }
            values.computeIfPresent(targetId, (key, value) -> value.published());
            currentReleaseId = targetId;
            return true;
        }

        private void addPublished(String id, String versionId) {
            add(id, versionId, "PUBLISHED");
            currentReleaseId = id;
        }

        private void addRetired(String id, String versionId) { add(id, versionId, "RETIRED"); }

        private void add(String id, String versionId, String status) {
            values.put(id, new KnowledgeIndexReleasePO(
                    id, "base-1", values.size() + 1, status, 1, 1,
                    "text-embedding-v4", 1024, "d".repeat(64), null,
                    "1", LocalDateTime.now(), "PUBLISHED".equals(status) ? LocalDateTime.now() : null));
            members.put(id, List.of(new KnowledgeIndexReleaseDocumentPO(
                    id, "document-1", versionId, "a".repeat(64), LocalDateTime.now())));
        }
    }
}
