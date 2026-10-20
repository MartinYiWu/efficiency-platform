package com.aiep.knowledge.application;

import com.aiep.knowledge.api.KnowledgeFacade;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnBean({KnowledgeBaseService.class, KnowledgeDocumentService.class, KnowledgeReleaseService.class})
public class KnowledgeFacadeImpl implements KnowledgeFacade {
    private final KnowledgeBaseService bases;
    private final KnowledgeDocumentService documents;
    private final KnowledgeReleaseService releases;

    public KnowledgeFacadeImpl(
            KnowledgeBaseService bases,
            KnowledgeDocumentService documents,
            KnowledgeReleaseService releases) {
        this.bases = bases;
        this.documents = documents;
        this.releases = releases;
    }

    @Override public KnowledgeViews.KnowledgeBaseView getKnowledgeBase(String id) { return bases.get(id); }
    @Override public KnowledgeViews.DocumentVersionView getDocumentVersion(String id) { return documents.getVersion(id); }
    @Override public KnowledgeViews.IndexReleaseView resolvePublishedIndex(String knowledgeBaseId) {
        return releases.resolvePublishedIndex(knowledgeBaseId);
    }
}
