package com.aiep.knowledge.api;

import com.aiep.knowledge.application.KnowledgeViews;

/** Cross-module contract for knowledge ownership and visibility queries. */
public interface KnowledgeFacade {
    default java.util.List<KnowledgeSourceEvent> pendingSourceEvents(int limit){return java.util.List.of();}
    default void acknowledgeSourceEvent(String eventId){throw new UnsupportedOperationException("KB_SOURCE_EVENTS_REQUIRED");}
    /** 严格当前Identity/tenant/KB可见范围和发布成员；默认旧实现拒绝，不复用legacy dev授权。 */
    default KnowledgeSourceSnapshot currentSourceSnapshot(com.aiep.identity.api.IdentityFacade.Subject actor,String knowledgeBaseId,String expectedReleaseId) {
        throw new UnsupportedOperationException("KB_SOURCE_METADATA_AUTHORITY_REQUIRED");
    }
    KnowledgeViews.KnowledgeBaseView getKnowledgeBase(String id);
    KnowledgeViews.DocumentVersionView getDocumentVersion(String id);
    KnowledgeViews.IndexReleaseView resolvePublishedIndex(String knowledgeBaseId);
}
