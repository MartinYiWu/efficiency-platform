package com.aiep.knowledge.application;

import com.aiep.knowledge.api.KnowledgeFacade;
import org.springframework.stereotype.Service;

@Service
public class KnowledgeFacadeImpl implements KnowledgeFacade {
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private KnowledgeSourceAuthorityService sourceAuthority;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.knowledge.repository.KnowledgeSourceEventRepository sourceEvents;
    @Override public java.util.List<com.aiep.knowledge.api.KnowledgeSourceEvent> pendingSourceEvents(int limit){return sourceEvents==null?java.util.List.of():sourceEvents.pending(limit);}
    @Override public void acknowledgeSourceEvent(String id){if(sourceEvents==null)throw new KnowledgeException("KB_SOURCE_EVENTS_REQUIRED","知识事件未装配");sourceEvents.acknowledge(id);}
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
    @Override public com.aiep.knowledge.api.KnowledgeSourceSnapshot currentSourceSnapshot(com.aiep.identity.api.IdentityFacade.Subject actor,String base,String release) {
        if(sourceAuthority==null)throw new KnowledgeException("KB_SOURCE_METADATA_AUTHORITY_REQUIRED","知识来源当前权威尚未装配");
        return sourceAuthority.snapshot(actor,base,release);
    }
    @Override public KnowledgeViews.DocumentVersionView getDocumentVersion(String id) { return documents.getVersion(id); }
    @Override public KnowledgeViews.IndexReleaseView resolvePublishedIndex(String knowledgeBaseId) {
        return releases.resolvePublishedIndex(knowledgeBaseId);
    }
}
