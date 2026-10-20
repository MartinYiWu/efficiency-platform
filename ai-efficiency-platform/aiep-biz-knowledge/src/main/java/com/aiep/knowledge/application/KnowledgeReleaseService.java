package com.aiep.knowledge.application;

import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeDocumentPO;
import com.aiep.knowledge.repository.KnowledgeDocumentVersionPO;
import com.aiep.knowledge.repository.KnowledgeIndexReleaseDocumentPO;
import com.aiep.knowledge.repository.KnowledgeIndexReleasePO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.knowledge.repository.KnowledgeReleaseMappers;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyRequest;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyView;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class KnowledgeReleaseService {
    private final KnowledgeMappers knowledge;
    private final KnowledgeReleaseMappers releases;
    private final AiInvokeFacade ai;
    private final TransactionTemplate transactions;

    public KnowledgeReleaseService(
            KnowledgeMappers knowledge,
            KnowledgeReleaseMappers releases,
            AiInvokeFacade ai,
            TransactionTemplate transactions) {
        this.knowledge = knowledge;
        this.releases = releases;
        this.ai = ai;
        this.transactions = transactions;
    }

    public KnowledgeViews.IndexReleaseView publishVersion(String versionId) {
        Candidate candidate = transactions.execute(status -> buildCandidate(versionId));
        if (candidate == null) {
            throw new IllegalStateException("候选索引事务未执行");
        }
        CustomerServiceIndexVerifyView verified;
        try {
            verified = ai.verifyCustomerServiceIndex(verifyRequest(candidate));
        } catch (RuntimeException exception) {
            failCandidate(candidate.release().id());
            throw new KnowledgeException("KB_INDEX_VERIFY_FAILED", "候选索引验证失败", exception);
        }
        if (!"READY".equals(verified.status())
                || verified.documentCount() != candidate.members().size()
                || verified.chunkCount() < candidate.members().size()
                || verified.checksum() == null
                || !verified.checksum().matches("[a-f0-9]{64}")) {
            failCandidate(candidate.release().id());
            throw new KnowledgeException("KB_INDEX_VERIFY_FAILED", "候选索引验证失败");
        }
        inTransaction(() -> releases.markReady(
                candidate.release().id(), verified.documentCount(),
                verified.chunkCount(), verified.checksum()));
        try {
            inTransaction(() -> activate(
                    candidate.release().knowledgeBaseId(), candidate.previousReleaseId(),
                    candidate.release().id()));
        } catch (KnowledgeException exception) {
            failCandidate(candidate.release().id());
            throw exception;
        }
        return view(candidate.release()
                .ready(verified.documentCount(), verified.chunkCount(), verified.checksum())
                .published());
    }

    public KnowledgeViews.IndexReleaseView rollback(String releaseId) {
        KnowledgeIndexReleasePO target = requiredRelease(releaseId);
        if (!List.of("READY", "RETIRED").contains(target.status())) {
            throw new KnowledgeException("KB_ROLLBACK_NOT_ALLOWED", "目标索引版本不可回滚");
        }
        KnowledgeBasePO base = requiredBase(target.knowledgeBaseId());
        inTransaction(() -> activate(
                target.knowledgeBaseId(), base.currentIndexReleaseId(), target.id()));
        return view(target.published());
    }

    public List<KnowledgeViews.IndexReleaseView> list(String knowledgeBaseId) {
        requiredBase(knowledgeBaseId);
        return releases.listReleases(knowledgeBaseId).stream()
                .map(KnowledgeReleaseService::view)
                .toList();
    }

    public KnowledgeViews.IndexReleaseView resolvePublishedIndex(String knowledgeBaseId) {
        KnowledgeBasePO base = requiredBase(knowledgeBaseId);
        if (base.currentIndexReleaseId() == null) {
            throw new KnowledgeException("KB_INDEX_NOT_PUBLISHED", "知识库尚未发布索引");
        }
        return view(requiredRelease(base.currentIndexReleaseId()));
    }

    private Candidate buildCandidate(String versionId) {
        KnowledgeDocumentVersionPO version = requiredVersion(versionId);
        if (!"READY".equals(version.status())) {
            throw new KnowledgeException("KB_VERSION_NOT_READY", "只有 READY 版本可以发布");
        }
        KnowledgeDocumentPO document = requiredDocument(version.documentId());
        knowledge.lockBase(document.knowledgeBaseId());
        KnowledgeBasePO base = requiredBase(document.knowledgeBaseId());
        List<KnowledgeIndexReleaseDocumentPO> snapshot = new ArrayList<>();
        if (base.currentIndexReleaseId() != null) {
            snapshot.addAll(releases.listDocuments(base.currentIndexReleaseId()));
        }
        snapshot.removeIf(member -> member.documentId().equals(document.id()));
        String releaseId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now();
        snapshot.add(new KnowledgeIndexReleaseDocumentPO(
                releaseId, document.id(), version.id(), version.fileSha256(), now));
        snapshot.sort(Comparator.comparing(KnowledgeIndexReleaseDocumentPO::documentId));
        List<KnowledgeIndexReleaseDocumentPO> members = snapshot.stream()
                .map(member -> new KnowledgeIndexReleaseDocumentPO(
                        releaseId, member.documentId(), member.documentVersionId(),
                        member.documentSha256(), now))
                .toList();
        KnowledgeIndexReleasePO release = new KnowledgeIndexReleasePO(
                releaseId, base.id(), releases.nextReleaseNo(base.id()), "BUILDING",
                members.size(), 0, "text-embedding-v4", 1024,
                membershipChecksum(members), base.currentIndexReleaseId(),
                KnowledgeBaseService.USER_ID, now, null);
        releases.insertRelease(release);
        releases.insertDocuments(members);
        return new Candidate(release, members, base.currentIndexReleaseId());
    }

    private void activate(String baseId, String expectedCurrentId, String targetId) {
        knowledge.lockBase(baseId);
        KnowledgeBasePO current = requiredBase(baseId);
        if (!Objects.equals(current.currentIndexReleaseId(), expectedCurrentId)
                || !releases.activate(baseId, expectedCurrentId, targetId)) {
            throw new KnowledgeException("KB_RELEASE_CONFLICT", "现网索引已被其他发布更新");
        }
    }

    private void failCandidate(String releaseId) {
        inTransaction(() -> releases.markFailed(releaseId));
    }

    private void inTransaction(Runnable action) {
        transactions.execute(status -> {
            action.run();
            return null;
        });
    }

    private CustomerServiceIndexVerifyRequest verifyRequest(Candidate candidate) {
        return new CustomerServiceIndexVerifyRequest(
                "customer-service-index-verify/1", candidate.release().id(),
                candidate.release().knowledgeBaseId(), candidate.members().stream()
                .map(member -> new CustomerServiceIndexVerifyRequest.DocumentMember(
                        member.documentId(), member.documentVersionId(),
                        member.documentSha256()))
                .toList());
    }

    private KnowledgeBasePO requiredBase(String id) {
        KnowledgeBasePO value = knowledge.findBase(KnowledgeBaseService.TENANT_ID, id);
        if (value == null) {
            throw new KnowledgeException("KB_BASE_NOT_FOUND", "知识库不存在");
        }
        return value;
    }

    private KnowledgeDocumentPO requiredDocument(String id) {
        KnowledgeDocumentPO value = knowledge.findDocument(id);
        if (value == null) {
            throw new KnowledgeException("KB_DOCUMENT_NOT_FOUND", "文档不存在");
        }
        return value;
    }

    private KnowledgeDocumentVersionPO requiredVersion(String id) {
        KnowledgeDocumentVersionPO value = knowledge.findVersion(id);
        if (value == null) {
            throw new KnowledgeException("KB_VERSION_NOT_FOUND", "文档版本不存在");
        }
        return value;
    }

    private KnowledgeIndexReleasePO requiredRelease(String id) {
        KnowledgeIndexReleasePO value = releases.findRelease(id);
        if (value == null) {
            throw new KnowledgeException("KB_INDEX_RELEASE_NOT_FOUND", "索引版本不存在");
        }
        return value;
    }

    private static String membershipChecksum(List<KnowledgeIndexReleaseDocumentPO> members) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (KnowledgeIndexReleaseDocumentPO member : members) {
                digest.update((member.documentId() + ":" + member.documentVersionId()
                        + ":" + member.documentSha256() + "\n").getBytes(StandardCharsets.UTF_8));
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前运行时不支持 SHA-256", exception);
        }
    }

    private static KnowledgeViews.IndexReleaseView view(KnowledgeIndexReleasePO value) {
        return new KnowledgeViews.IndexReleaseView(
                value.id(), value.knowledgeBaseId(), value.releaseNo(), value.status(),
                value.documentCount(), value.chunkCount(), value.embeddingModel(),
                value.embeddingDimension(), value.checksum(), value.previousReleaseId(),
                value.createdAt(), value.publishedAt());
    }

    private record Candidate(
            KnowledgeIndexReleasePO release,
            List<KnowledgeIndexReleaseDocumentPO> members,
            String previousReleaseId) { }
}
