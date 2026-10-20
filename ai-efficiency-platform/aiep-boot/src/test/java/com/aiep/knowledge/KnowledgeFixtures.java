package com.aiep.knowledge;

import static org.mockito.Mockito.mock;

import com.aiep.knowledge.application.KnowledgeDocumentService;
import com.aiep.knowledge.repository.KnowledgeBasePO;
import com.aiep.knowledge.repository.KnowledgeIngestItemPO;
import com.aiep.knowledge.repository.KnowledgeMappers;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformfile.api.FileFacade;
import java.time.LocalDateTime;
import org.springframework.transaction.support.TransactionTemplate;

final class KnowledgeFixtures {
    static final LocalDateTime NOW = LocalDateTime.of(2026, 10, 20, 12, 0);

    private KnowledgeFixtures() {
    }

    static KnowledgeBasePO activeBase() {
        return new KnowledgeBasePO(
                "base-1", "dev", "POLICY", "公司制度", null, "COMPANY_POLICY",
                "COMPANY_WIDE", null, "ACTIVE", null, "1", NOW, "1", NOW);
    }

    static KnowledgeIngestItemPO item(String id, String status, String errorCode) {
        return item(id, status, errorCode, null);
    }

    static KnowledgeIngestItemPO item(String id, String status, String errorCode, String retryOf) {
        return new KnowledgeIngestItemPO(
                id, "batch-1", null, null, null, status, errorCode,
                errorCode == null ? null : "安全错误摘要", retryOf, NOW, NOW,
                "FAILED".equals(status) || "SUCCEEDED".equals(status) ? NOW : null);
    }

    static KnowledgeDocumentService documentService() {
        return new KnowledgeDocumentService(
                mock(KnowledgeMappers.class),
                mock(FileFacade.class),
                mock(AiInvokeFacade.class),
                mock(TransactionTemplate.class));
    }
}
