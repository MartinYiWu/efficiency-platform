package com.aiep.knowledge.application;

import com.aiep.identity.api.IdentityFacade;
import com.aiep.knowledge.api.KnowledgeSourceSnapshot;
import com.aiep.knowledge.repository.KnowledgeSourceMetadataRepository;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 真实知识元数据权威；旧dev常量、配置管理权和模型引用均不能替代本人的当前读授权。 */
@Service
public class KnowledgeSourceAuthorityService {
    private final boolean enabled;private final IdentityFacade identity;private final KnowledgeSourceMetadataRepository repository;
    public KnowledgeSourceAuthorityService(@Value("${aiep.knowledge.memory-source-metadata-enabled:false}") boolean enabled,IdentityFacade identity,KnowledgeSourceMetadataRepository repository){this.enabled=enabled;this.identity=identity;this.repository=repository;}
    @Transactional(readOnly=true)
    public KnowledgeSourceSnapshot snapshot(IdentityFacade.Subject original,String base,String release) {
        if(!enabled)throw denied("KB_SOURCE_METADATA_DISABLED");
        if(original==null||original.sessionRef()==null||base==null||base.isBlank()||release==null||release.isBlank())throw denied("KB_SOURCE_IDENTITY_REQUIRED");
        var actor=identity.refresh(original.tenantId(),original.userId(),original.sessionRef()).orElseThrow(()->denied("KB_SOURCE_IDENTITY_REQUIRED"));
        if(!actor.tenantId().equals(original.tenantId())||!actor.userId().equals(original.userId())||!actor.sessionRef().equals(original.sessionRef())||!actor.permissions().contains("knowledge:read"))throw denied("KB_SOURCE_ACCESS_DENIED");
        var rows=repository.snapshot(actor.tenantId(),base,release);
        if(rows.isEmpty()||rows.size()>128||rows.getFirst().documentCount()!=rows.size())throw denied("KB_SOURCE_DIRECTORY_INCOMPLETE");
        var first=rows.getFirst();var documents=new ArrayList<KnowledgeSourceSnapshot.Document>();var ids=new HashSet<String>();
        for(var row:rows) {
            if(!actor.tenantId().equals(row.tenantId())||!base.equals(row.knowledgeBaseId())||!release.equals(row.releaseId())
                    ||!"ACTIVE".equals(row.baseStatus())||!"PUBLISHED".equals(row.releaseStatus())
                    ||!"ACTIVE".equals(row.documentStatus())||!"PUBLISHED".equals(row.versionStatus())
                    ||row.documentVersionId()==null||!row.documentVersionId().equals(row.currentPublishedVersionId())
                    ||row.fileSha256()==null||!row.fileSha256().matches("[0-9a-f]{64}")||!row.fileSha256().equals(row.memberSha256())
                    ||row.releaseChecksum()==null||!row.releaseChecksum().matches("[0-9a-f]{64}")
                    ||row.effectiveDate()!=null&&row.effectiveDate().isAfter(LocalDate.now(ZoneOffset.UTC))||!ids.add(row.documentVersionId()))throw denied("KB_SOURCE_DIRECTORY_CHANGED");
            if(!"COMPANY_WIDE".equals(row.visibilityScope())&&!("DEPARTMENT".equals(row.visibilityScope())&&row.ownerDepartmentId()!=null&&actor.departmentIds().contains(row.ownerDepartmentId())))throw denied("KB_SOURCE_ACCESS_DENIED");
            documents.add(new KnowledgeSourceSnapshot.Document(row.documentId(),row.documentVersionId(),row.fileSha256()));
        }
        return new KnowledgeSourceSnapshot(actor.tenantId(),base,release,first.releaseChecksum(),Instant.now(),documents);
    }
    private static KnowledgeException denied(String code){return new KnowledgeException(code,"知识来源当前授权或发布目录无法验证");}
}
