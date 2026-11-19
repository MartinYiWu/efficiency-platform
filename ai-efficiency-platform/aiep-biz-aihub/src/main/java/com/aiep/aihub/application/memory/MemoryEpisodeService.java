package com.aiep.aihub.application.memory;

import static com.aiep.aihub.application.memory.MemoryScopeMembershipService.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 人工确认的有界经验与脱敏审批；点赞不修改事实等级，私密来源不因摘要自动共享。 */
@Service
public class MemoryEpisodeService {
    static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
    final MemoryEpisodeMapper mapper;final MemoryMapper memories;final MemoryDependencyService dependencies;
    final MemoryValueCodec codec;final TransactionTemplate transaction;final MemoryScopeMembershipService memberships;
    private final MemoryPacketMapper packets;private final MemoryScopePolicy scopes;private final MemorySessionBindingService bindings;
    private final MemorySummarySourceService sourceFacts;
    private final IdentityFacade identity;private final boolean enabled;
    public MemoryEpisodeService(@Value("${aiep.memory.episodes-enabled:false}") boolean enabled,MemoryEpisodeMapper mapper,
            MemoryMapper memories,MemoryPacketMapper packets,MemoryDependencyService dependencies,MemoryValueCodec codec,
            MemoryScopePolicy scopes,MemorySessionBindingService bindings,IdentityFacade identity,MemorySummarySourceService sourceFacts,
            MemoryScopeMembershipService memberships,PlatformTransactionManager manager) {
        this.enabled=enabled;this.mapper=mapper;this.memories=memories;this.packets=packets;this.dependencies=dependencies;this.codec=codec;
        this.scopes=scopes;this.bindings=bindings;this.identity=identity;this.sourceFacts=sourceFacts;this.memberships=memberships;transaction=new TransactionTemplate(manager);
        transaction.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    IdentityFacade.Subject current(IdentityFacade.Subject actor,String permission) {
        if(!enabled)throw failure("FEATURE_DISABLED");
        if(actor==null||actor.sessionRef()==null)throw failure("MEMORY_IDENTITY_REQUIRED");
        var live=identity.refresh(actor.tenantId(),actor.userId(),actor.sessionRef()).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
        if(!actor.tenantId().equals(live.tenantId())||!actor.userId().equals(live.userId())||!actor.sessionRef().equals(live.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");
        if(permission!=null&&!live.permissions().contains(permission))throw failure("MEMORY_SCOPE_DENIED");return live;
    }
    private void authorize(IdentityFacade.Subject actor,MemoryScopeDTO scope){scopes.require(actor,scope,Set.of());bindings.require(actor,scope);codec.currentVersion();}
    JsonNode policy(EpisodePO row){return policy(scope(row));}
    private JsonNode policy(MemoryScopeDTO scope) {
        var published=sourceFacts.mapper.lockPublishedPolicy(b(scope.tenantId()),scope.domain());MemoryPolicyService.requireArtifactPolicy(published);
        try {var config=JSON.readTree(published.policyJson()).path("episodes");if(!config.path("enabled").isBoolean()||!config.path("enabled").booleanValue())throw failure("FEATURE_DISABLED");return config;}
        catch(java.io.IOException invalid){throw failure("FEATURE_DISABLED");}
    }
    public EpisodeView create(IdentityFacade.Subject original,CreateCommand command) {
        var actor=current(original,"memory:episode:create");if(command==null||command.content()==null)throw failure("MEMORY_EPISODE_INVALID");
        authorize(actor,command.scope());id(command.executionId());id(command.idempotencyKey());
        return transaction.execute(tx->{
            var scope=command.scope();var packet=packets.findPacket(b(scope.tenantId()),b(command.executionId()));
            if(packet==null||!Arrays.equals(packet.userId(),b(actor.userId()))||!JSON.valueToTree(scope).equals(tree(packet.scopeJson())))throw failure("MEMORY_SCOPE_DENIED");
            var closure=dependencies.dependencies(scope,"EXECUTION",command.executionId(),"1");if(closure.isEmpty()||closure.size()>512)throw failure("MEMORY_EPISODE_SOURCE_REQUIRED");
            var config=policy(scope);requireTypes(config.path("sourceTypes"),closure);var deadline=dependencies.requireCurrent(scope,closure);
            for(var dependency:closure)if(Set.of("MESSAGE","CURRENT_USER_MESSAGE").contains(dependency.sourceType()))sourceFacts.requireInputMessages(scope,List.of(dependency));
            validateEvidence(command.content(),scope,closure);
            long retention=config.path("retentionSeconds").isIntegralNumber()?config.path("retentionSeconds").longValue():0;
            if(retention<1||retention>15552000)throw failure("FEATURE_DISABLED");
            Instant expires=Instant.now().plusSeconds(retention);if(deadline.isBefore(expires))expires=deadline;
            String fingerprint=MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(actor.userId(),command)));
            var prior=mapper.findEpisodeRequest(b(actor.tenantId()),b(command.idempotencyKey()));
            if(prior!=null){if(!fingerprint.equals(prior.fingerprint()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return view(actor,scope,prior);}
            byte[] id=uuid();var sealed=codec.seal(b(actor.tenantId()),id,b("original"),json(command.content()));
            var published=memories.findPublishedPolicy(b(actor.tenantId()),scope.domain());
            var row=new EpisodePO(b(actor.tenantId()),id,b(actor.userId()),scope.domain(),scope.sessionId()==null?null:b(scope.sessionId()),b(command.executionId()),json(scope),json(closure),published.id(),published.versionId(),"CANDIDATE",0,expires,sealed.keyVersion(),sealed.payload(),sealed.nonce(),sealed.tag(),sealed.hmac(),null,null,null,null,null,null,null,null,b(command.idempotencyKey()),fingerprint);
            one(mapper.insertEpisode(row));for(var dep:closure)one(packets.insertDependency(row.tenantId(),b(dep.sourceId()),"EPISODE",id,b("1"),null,dep.grantEpoch(),dep.sourceEpoch(),dep.deletionEpoch()));return view(actor,scope,row);
        });
    }
    /** 没有现有可信测量/去身份技术事件投影时拒绝，不能把模型或人工自由文本当真实测量。 */
    static void validateEvidence(Content content,MemoryScopeDTO scope,List<Dependency> closure) {
        Set<String> ids=new HashSet<>();closure.forEach(dep->ids.add(dep.sourceId()));
        if(!ids.containsAll(content.evidenceRefs()))throw failure("MEMORY_EPISODE_EVIDENCE_MISMATCH");
        if("MEASURED_RESULT".equals(content.category()))throw failure("MEMORY_EPISODE_MEASUREMENT_AUTHORITY_REQUIRED");
        if("hr".equals(scope.domain())&&(!"TECHNICAL_EXPERIENCE".equals(content.category())||closure.stream().anyMatch(dep->!"TECHNICAL_EVENT".equals(dep.sourceType()))))throw failure("MEMORY_EPISODE_HR_SOURCE_DENIED");
        if("TECHNICAL_EXPERIENCE".equals(content.category())&&closure.stream().noneMatch(dep->"TECHNICAL_EVENT".equals(dep.sourceType())))throw failure("MEMORY_EPISODE_TECHNICAL_AUTHORITY_REQUIRED");
    }
    public List<EpisodeView> list(IdentityFacade.Subject original,MemoryScopeDTO scope) {
        var actor=current(original,null);authorize(actor,scope);return transaction.execute(tx->mapper.listEpisodes(b(actor.tenantId()),b(actor.userId()),scope.domain(),scope.sessionId()==null?null:b(scope.sessionId())).stream().map(row->view(actor,scope,refresh(row))).toList());
    }
    public EpisodeView get(IdentityFacade.Subject original,MemoryScopeDTO scope,String id) {var actor=current(original,null);authorize(actor,scope);return transaction.execute(tx->view(actor,scope,refresh(load(actor.tenantId(),id))));}
    public List<EpisodeView> shared(IdentityFacade.Subject original,String scopeId) {
        var actor=current(original,null);return transaction.execute(tx->{var acl=memberships.scope(actor.tenantId(),scopeId);
            boolean approver=Arrays.equals(acl.approverId(),b(actor.userId()));
            if(approver)memberships.requireApprover(actor,acl);else memberships.requireMember(actor,acl);
            return mapper.listShared(acl.tenantId(),acl.id()).stream().map(this::refresh).filter(row->"SHARED".equals(row.status())||approver&&"SHARE_PENDING".equals(row.status()))
                    .map(row->view(actor,scope(row),row)).toList();});
    }
    public EpisodeView decide(IdentityFacade.Subject original,MemoryScopeDTO scope,String id,long expected,String action,String request) {
        var actor=current(original,"memory:episode:confirm");authorize(actor,scope);id(request);
        if(!Set.of("CONFIRM","REJECT").contains(action))throw failure("MEMORY_EPISODE_INVALID");
        return transaction.execute(tx->{var row=refresh(load(actor.tenantId(),id));owner(actor,row);requireScope(scope,row);
            if(!"CANDIDATE".equals(row.status())||row.revision()!=expected)throw failure("MEMORY_EPISODE_REVISION_CONFLICT");
            one(mapper.transition(row,"CONFIRM".equals(action)?"CONFIRMED":"REJECTED"));return view(actor,scope,load(actor.tenantId(),id));});
    }
    public EpisodeView requestShare(IdentityFacade.Subject original,MemoryScopeDTO scope,String id,long expected,String scopeId,Content deidentified,String request) {
        var actor=current(original,"memory:episode:share");authorize(actor,scope);id(request);id(scopeId);
        return transaction.execute(tx->{var row=refresh(load(actor.tenantId(),id));owner(actor,row);requireScope(scope,row);
            if(!"CONFIRMED".equals(row.status())||row.revision()!=expected)throw failure("MEMORY_EPISODE_REVISION_CONFLICT");
            var acl=memberships.scope(actor.tenantId(),scopeId);memberships.requireMember(actor,acl);
            if(row.expiresAt().isAfter(acl.expiresAt()))throw failure("MEMORY_SHARING_RETENTION_DENIED");
            requireShareSources(actor,row);
            var closure=closure(row);
            validateEvidence(deidentified,scope,closure);
            var sealed=codec.seal(row.tenantId(),row.id(),b("shared"),json(deidentified));
            one(mapper.requestShare(row,acl.id(),b(actor.sessionRef()),new SharedPO(sealed.keyVersion(),sealed.payload(),sealed.nonce(),sealed.tag(),sealed.hmac())));return view(actor,scope,load(actor.tenantId(),id));});
    }
    public EpisodeView approveShare(IdentityFacade.Subject original,String id,long expected,String request) {
        var actor=current(original,"memory:episode:approve");id(request);
        return transaction.execute(tx->{var row=refresh(load(actor.tenantId(),id));
            if(row.shareScopeId()==null||Arrays.equals(row.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");
            var acl=memberships.scope(actor.tenantId(),text(row.shareScopeId()));memberships.requireApprover(actor,acl);memberships.requireActive(acl);
            if(!"SHARE_PENDING".equals(row.status())||row.revision()!=expected)throw failure("MEMORY_EPISODE_REVISION_CONFLICT");
            if(row.shareOwnerSessionRef()==null)throw failure("MEMORY_SCOPE_DENIED");
            var owner=identity.refresh(text(row.tenantId()),text(row.ownerId()),text(row.shareOwnerSessionRef())).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
            if(!text(row.ownerId()).equals(owner.userId())||!text(row.tenantId()).equals(owner.tenantId())||!text(row.shareOwnerSessionRef()).equals(owner.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");
            requireShareSources(owner,row);
            one(mapper.approveShare(row,b(actor.userId())));return view(actor,scope(row),load(actor.tenantId(),id));});
    }
    public EpisodeView like(IdentityFacade.Subject original,MemoryScopeDTO scope,String id) {
        var actor=current(original,null);return transaction.execute(tx->{var row=refresh(load(actor.tenantId(),id));view(actor,scope,row);mapper.insertLike(row.tenantId(),row.id(),b(actor.userId()));return view(actor,scope,row);});
    }
    /** 分享正文是owner人工新写的case；每个原始源用途/归属再次核验，不分享原文访问权。 */
    private void requireShareSources(IdentityFacade.Subject owner,EpisodePO row) {
        var scope=scope(row);authorize(owner,scope);var closure=closure(row);var config=policy(row);
        requireTypes(config.path("shareableSourceTypes"),closure);dependencies.requireCurrent(scope,closure);
        for(var dep:closure) {
            var uses=config.path("sourcePurposes").path(dep.sourceType());
            if(!uses.isArray()||!hasText(uses,"SHARED_EPISODE"))throw failure("MEMORY_EPISODE_PURPOSE_DENIED");
            if(Set.of("MESSAGE","CURRENT_USER_MESSAGE").contains(dep.sourceType())) {
                if(!"operations".equals(scope.domain()))throw failure("MEMORY_EPISODE_PRIVATE_SOURCE_DENIED");
                sourceFacts.requireInputMessages(scope,List.of(dep));
            } else if("USER_PREFERENCE_DECISION".equals(dep.sourceType())) {
                var basis=sourceFacts.mapper.findBasis(row.tenantId(),b(dep.sourceId()));
                if(basis==null||!Arrays.equals(basis.ownerId(),row.ownerId())||!Arrays.equals(basis.actorId(),row.ownerId())||!scope.domain().equals(basis.domain())
                        ||!scope.topLevelAgentId().equals(basis.originTopAgentId())||!Arrays.equals(basis.versionId(),b(dep.sourceVersion())))throw failure("MEMORY_EPISODE_PRIVATE_SOURCE_DENIED");
            } else throw failure("MEMORY_EPISODE_PRIVATE_SOURCE_DENIED");
        }
        if(row.expiresAt().isAfter(dependencies.requireCurrent(scope,closure)))throw failure("MEMORY_SHARING_RETENTION_DENIED");
    }
    private static boolean hasText(JsonNode array,String value){for(var node:array)if(node.isTextual()&&value.equals(node.textValue()))return true;return false;}
    public EpisodeView withdraw(IdentityFacade.Subject original,MemoryScopeDTO scope,String id,long expected,String request) {
        var actor=current(original,"memory:episode:confirm");id(request);return transaction.execute(tx->{var row=load(actor.tenantId(),id);owner(actor,row);requireScope(scope,row);
            if(row.revision()!=expected||"REVOKED".equals(row.status()))throw failure("MEMORY_EPISODE_REVISION_CONFLICT");one(mapper.scrub(row));return view(actor,scope,load(actor.tenantId(),id));});
    }
    EpisodePO load(String tenant,String id){var row=mapper.lockEpisode(b(tenant),b(id));if(row==null)throw failure("MEMORY_NOT_FOUND");return row;}
    EpisodePO refresh(EpisodePO row) {
        if("REVOKED".equals(row.status()))return row;
        try {if(!row.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SOURCE_CHANGED");dependencies.requireCurrent(scope(row),closure(row));
            for(var dependency:closure(row))if(Set.of("MESSAGE","CURRENT_USER_MESSAGE").contains(dependency.sourceType()))sourceFacts.requireInputMessages(scope(row),List.of(dependency));
            var published=memories.findPublishedPolicy(row.tenantId(),row.domain());if(published==null||!Arrays.equals(published.id(),row.policyId())||!Arrays.equals(published.versionId(),row.policyVersionId()))throw failure("MEMORY_SOURCE_CHANGED");policy(row);
            if(row.shareScopeId()!=null) {
                if(row.shareOwnerSessionRef()==null)throw failure("MEMORY_SCOPE_DENIED");
                var owner=identity.refresh(text(row.tenantId()),text(row.ownerId()),text(row.shareOwnerSessionRef())).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
                if(!text(row.ownerId()).equals(owner.userId())||!text(row.tenantId()).equals(owner.tenantId())||!text(row.shareOwnerSessionRef()).equals(owner.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");
                requireShareSources(owner,row);
            }
        }catch(MemoryException invalid){if(Set.of("MEMORY_STORAGE_UNAVAILABLE","MEMORY_KEY_UNAVAILABLE").contains(invalid.code()))throw invalid;one(mapper.scrub(row));return load(text(row.tenantId()),text(row.id()));}return row;
    }
    Content content(EpisodePO row,boolean shared){var sealed=shared?new MemoryValueCodec.Sealed(row.sharedPayload(),row.sharedNonce(),row.sharedTag(),row.sharedHmac(),row.sharedKeyVersion()):new MemoryValueCodec.Sealed(row.encryptedPayload(),row.nonce(),row.authTag(),row.contentHmac(),row.keyVersion());return read(codec.openSealed(row.tenantId(),row.id(),b(shared?"shared":"original"),sealed),new TypeReference<Content>(){});}
    void readableShared(IdentityFacade.Subject actor,EpisodePO row){if(!"SHARED".equals(row.status())||row.shareScopeId()==null)throw failure("MEMORY_SCOPE_DENIED");memberships.requireMember(actor,memberships.scope(actor.tenantId(),text(row.shareScopeId())));}
    private EpisodeView view(IdentityFacade.Subject actor,MemoryScopeDTO requested,EpisodePO row) {
        boolean owner=Arrays.equals(row.ownerId(),b(actor.userId()));
        if(owner)requireScope(requested,row);
        else if(row.shareScopeId()!=null&&actor.permissions().contains("memory:episode:approve")
                &&Arrays.equals(memberships.scope(actor.tenantId(),text(row.shareScopeId())).approverId(),b(actor.userId()))) {
            var acl=memberships.scope(actor.tenantId(),text(row.shareScopeId()));memberships.requireApprover(actor,acl);memberships.requireActive(acl);
        } else readableShared(actor,row);
        return new EpisodeView(text(row.id()),row.domain(),!owner||row.sessionId()==null?null:text(row.sessionId()),"REVOKED".equals(row.status())?null:content(row,!owner),row.status(),row.revision(),row.expiresAt(),mapper.countLikes(row.tenantId(),row.id()));
    }
    static void requireScope(MemoryScopeDTO requested,EpisodePO row){if(!JSON.valueToTree(requested).equals(tree(row.scopeJson())))throw failure("MEMORY_SCOPE_DENIED");}
    static void owner(IdentityFacade.Subject actor,EpisodePO row){if(!Arrays.equals(row.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");}
    MemoryScopeDTO scope(EpisodePO row){return read(row.scopeJson(),new TypeReference<MemoryScopeDTO>(){});}
    List<Dependency> closure(EpisodePO row){return read(row.dependenciesJson(),new TypeReference<List<Dependency>>(){});}
    private static void requireTypes(JsonNode permitted,List<Dependency> closure){if(!permitted.isArray())throw failure("FEATURE_DISABLED");var types=new HashSet<String>();permitted.forEach(node->{if(!node.isTextual())throw failure("FEATURE_DISABLED");types.add(node.textValue());});if(closure.stream().anyMatch(dep->!types.contains(dep.sourceType())))throw failure("MEMORY_EPISODE_SOURCE_DENIED");}
    static JsonNode tree(String value){try{return JSON.readTree(value);}catch(Exception invalid){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static <T>T read(String value,TypeReference<T> type){try{return JSON.readValue(value,type);}catch(Exception invalid){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static String json(Object value){try{return JSON.writeValueAsString(value);}catch(Exception invalid){throw failure("MEMORY_EPISODE_INVALID");}}
}
