package com.aiep.knowledge.api;

import com.aiep.knowledge.application.KnowledgeViews;

/** Cross-module contract for knowledge ownership and visibility queries. */
public interface KnowledgeFacade {
    KnowledgeViews.KnowledgeBaseView getKnowledgeBase(String id);
    KnowledgeViews.DocumentVersionView getDocumentVersion(String id);
    KnowledgeViews.IndexReleaseView resolvePublishedIndex(String knowledgeBaseId);
}
