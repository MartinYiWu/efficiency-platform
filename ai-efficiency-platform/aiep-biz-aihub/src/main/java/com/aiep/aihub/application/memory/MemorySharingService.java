package com.aiep.aihub.application.memory;

import static com.aiep.aihub.application.memory.MemoryScopeMembershipService.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemorySharingContracts.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.repository.memory.MemorySharingMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 共享只投影明确USER决定的白名单值；原文/摘要/模型派生来源不能借ACL出域。 */
@Service
public class MemorySharingService {
    private static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
    private final MemoryScopeMembershipService memberships;private final MemorySharingMapper mapper;
    private final MemoryMapper memories;private final MemoryPacketMapper packets;private final MemoryDependencyService dependencies;
    private final MemoryPolicyService policies;private final MemoryValueCodec codec;
    public MemorySharingService(MemoryScopeMembershipService memberships,MemorySharingMapper mapper,MemoryMapper memories,
            MemoryPacketMapper packets,MemoryDependencyService dependencies,MemoryPolicyService policies,MemoryValueCodec codec) {
        this.memberships=memberships;this.mapper=mapper;this.memories=memories;this.packets=packets;this.dependencies=dependencies;this.policies=policies;this.codec=codec;
    }
    public boolean enabled(){return memberships.enabled();}
    private record Value(MemoryItemPO item,VersionRow version,List<Dependency> dependencies,String value,Instant expiresAt) { }
    /** 原已确认版本的每个源必须是同一个USER决策；含聊天/提议传递源即拒绝共享。 */
    private Value source(String tenant,String owner,String origin,String itemId,String versionId,long revision) {
        if(!com.aiep.aihub.api.memory.MemorySharingContracts.AGENTS.contains(origin))throw failure("MEMORY_SCOPE_DENIED");
        var item=memories.findItemForUpdate(b(tenant),b(itemId));
        if(item==null||!Arrays.equals(item.ownerId(),b(owner))||!Arrays.equals(item.subjectId(),b(owner))||!"USER".equals(item.subjectType())
                ||!origin.equals(item.domain())||!origin.equals(item.originTopAgentId())||!"USER_PRIVATE".equals(item.scopeType())
                ||!Arrays.equals(item.scopeId(),MemoryMapper.privateScope(owner,origin))||!"assistant_response".equals(item.purpose())
                ||!com.aiep.aihub.api.memory.MemorySharingContracts.FIELDS.contains(item.fieldKey())||!"LIVE".equals(item.lifecycle())
                ||item.revision()!=revision||!Arrays.equals(item.currentVersionId(),b(versionId)))throw failure("MEMORY_SOURCE_CHANGED");
        var version=memories.findPreferenceVersion(b(tenant),item.id(),b(versionId));
        if(version==null||!"ACTIVE".equals(version.status())||!version.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SOURCE_CHANGED");
        var originScope=new MemoryScopeDTO(tenant,owner,origin,origin,"TASK_ONLY",null);
        var closure=dependencies.dependencies(originScope,"MEMORY_VERSION",itemId,versionId);
        if(closure.isEmpty()||closure.stream().anyMatch(dep->!"USER_PREFERENCE_DECISION".equals(dep.sourceType())||!versionId.equals(dep.sourceVersion())))throw failure("MEMORY_SHARING_SOURCE_DENIED");
        Instant sourceExpiry=dependencies.requireCurrent(originScope,closure);
        for(var dep:closure){var state=packets.findSource(b(tenant),b(dep.sourceId()));if(state==null||state.blocked()||!Arrays.equals(state.sourceVersion(),version.id()))throw failure("MEMORY_SOURCE_CHANGED");}
        policies.requireVersionArtifacts(b(tenant),List.of(new VersionIdentityPO(item.id(),version.id())));
        String value=codec.open(version);policy(tenant,owner,origin,item.fieldKey(),value);return new Value(item,version,closure,value,sourceExpiry.isBefore(version.expiresAt())?sourceExpiry:version.expiresAt());
    }
    private void policy(String tenant,String user,String agent,String field,String value) {
        policies.require(new MemoryScopeDTO(tenant,user,agent,agent,"TASK_ONLY",null),field,value);
        var row=memories.findPublishedPolicy(b(tenant),agent);MemoryPolicyService.requireArtifactPolicy(row);
        try {
            var node=JSON.readTree(row.policyJson()).path("sharing");
            if(!node.path("enabled").isBoolean()||!node.path("enabled").booleanValue()||!node.path("fields").isArray())throw failure("FEATURE_DISABLED");
            var fields=JSON.convertValue(node.path("fields"),new TypeReference<List<String>>(){});
            if(!fields.contains(field)||!com.aiep.aihub.api.memory.MemorySharingContracts.FIELDS.containsAll(fields))throw failure("MEMORY_SHARING_FIELD_DENIED");
        }catch(java.io.IOException invalid){throw failure("FEATURE_DISABLED");}
    }
    private Instant expiry(Instant requested,Instant source,Instant scope) {
        if(requested==null||!requested.isAfter(Instant.now())||requested.isAfter(source)||requested.isAfter(Instant.now().plusSeconds(15552000))
                ||scope!=null&&requested.isAfter(scope))throw failure("MEMORY_SHARING_RETENTION_DENIED");return requested;
    }
    private List<String> agents(List<String> allowed) {
        if(allowed==null||allowed.isEmpty()||allowed.size()>2||!com.aiep.aihub.api.memory.MemorySharingContracts.AGENTS.containsAll(allowed))throw failure("MEMORY_SCOPE_DENIED");
        return allowed.stream().distinct().sorted().toList();
    }
    public GrantView grantAgent(IdentityFacade.Subject original,GrantCommand command) {
        var actor=memberships.current(original);id(command.idempotencyKey());
        if(command.originAgent().equals(command.targetAgent()))throw failure("MEMORY_SHARING_INVALID");agents(List.of(command.targetAgent()));
        return memberships.transaction.execute(tx->{
            var value=source(actor.tenantId(),actor.userId(),command.originAgent(),command.itemId(),command.versionId(),command.expectedItemRevision());
            policy(actor.tenantId(),actor.userId(),command.targetAgent(),value.item().fieldKey(),value.value());
            var expires=expiry(command.expiresAt(),value.expiresAt(),null);String fingerprint=fingerprint(actor.userId(),command);
            var prior=mapper.findGrantRequest(b(actor.tenantId()),b(command.idempotencyKey()));
            if(prior!=null){if(!fingerprint.equals(prior.fingerprint()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return agentView(prior);}
            var grant=new GrantPO(b(actor.tenantId()),uuid(),null,b(actor.userId()),value.item().id(),value.version().id(),value.item().fieldKey(),command.originAgent(),json(List.of(command.targetAgent())),"ACTIVE",1,command.expectedItemRevision(),expires,b(command.idempotencyKey()),fingerprint);
            one(mapper.insertGrant(grant));project(grant,actor.userId(),command.targetAgent(),0);return agentView(grant);
        });
    }
    public List<GrantView> listAgentGrants(IdentityFacade.Subject original,String origin) {
        var actor=memberships.current(original);agents(List.of(origin));return memberships.transaction.execute(tx->mapper.listGrants(b(actor.tenantId()),b(actor.userId()),origin).stream().map(this::agentView).toList());
    }
    public ShareView requestShare(IdentityFacade.Subject original,String scopeId,ShareCommand command) {
        var actor=memberships.current(original);id(command.idempotencyKey());var allowed=agents(command.allowedAgents());
        return memberships.transaction.execute(tx->{
            var scope=memberships.scope(actor.tenantId(),scopeId);memberships.requireMember(actor,scope);
            var value=source(actor.tenantId(),actor.userId(),command.originAgent(),command.itemId(),command.versionId(),command.expectedItemRevision());
            for(String agent:allowed)policy(actor.tenantId(),actor.userId(),agent,value.item().fieldKey(),value.value());
            Instant expires=expiry(command.expiresAt(),value.expiresAt(),scope.expiresAt());String fingerprint=fingerprint(actor.userId(),scopeId,command);
            var prior=mapper.findGrantRequest(b(actor.tenantId()),b(command.idempotencyKey()));
            if(prior!=null){if(!fingerprint.equals(prior.fingerprint()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return shareView(prior);}
            var grant=new GrantPO(b(actor.tenantId()),uuid(),scope.id(),b(actor.userId()),value.item().id(),value.version().id(),value.item().fieldKey(),command.originAgent(),json(allowed),"PENDING",0,command.expectedItemRevision(),expires,b(command.idempotencyKey()),fingerprint);
            one(mapper.insertGrant(grant));return shareView(grant);
        });
    }
    public ShareView approveShare(IdentityFacade.Subject original,String shareId,RevisionCommand command) {
        var actor=memberships.current(original);id(command.idempotencyKey());return memberships.transaction.execute(tx->{
            var grant=grant(actor.tenantId(),shareId);if(grant.scopeId()==null)throw failure("MEMORY_SCOPE_DENIED");
            var scope=memberships.scope(actor.tenantId(),text(grant.scopeId()));memberships.requireActive(scope);memberships.requireApprover(actor,scope);
            if(Arrays.equals(grant.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");
            if(!"PENDING".equals(grant.status())||grant.revision()!=command.expectedRevision())throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            source(actor.tenantId(),text(grant.ownerId()),grant.originAgent(),text(grant.itemId()),text(grant.versionId()),grant.itemRevision());
            if(!grant.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SOURCE_CHANGED");one(mapper.updateGrant(grant,"ACTIVE"));
            grant=grant(actor.tenantId(),shareId);
            // 每位成员必须本人先ACCEPT；已批准的源只有显式共享USER偏好，没有源业务材料权限可扩张。
            for(var member:mapper.listMembers(scope.tenantId(),scope.id()))if("ACTIVE".equals(member.status()))for(String agent:allowed(grant))project(grant,text(member.userId()),agent,member.revision());
            return shareView(grant);
        });
    }
    public List<ShareView> listShares(IdentityFacade.Subject original,String scopeId) {
        var actor=memberships.current(original);return memberships.transaction.execute(tx->{
            var scope=memberships.scope(actor.tenantId(),scopeId);
            if(!Arrays.equals(scope.approverId(),b(actor.userId())))memberships.requireMember(actor,scope);
            return mapper.listScopeGrants(scope.tenantId(),scope.id()).stream().map(this::shareView).toList();
        });
    }
    public ScopeView membership(IdentityFacade.Subject original,String scopeId,MembershipCommand command) {
        var actor=memberships.current(original);id(command.idempotencyKey());return memberships.transaction.execute(tx->{
            var scope=memberships.scope(actor.tenantId(),scopeId);memberships.requireActive(scope);memberships.requireDepartment(actor,scope);
            var member=mapper.lockMember(scope.tenantId(),scope.id(),b(actor.userId()));
            if(member==null||member.revision()!=command.expectedRevision())throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            if("ACCEPT".equals(command.action())&&"INVITED".equals(member.status())) {
                one(mapper.updateMember(member,"ACTIVE",b(command.idempotencyKey())));var current=mapper.lockMember(scope.tenantId(),scope.id(),member.userId());
                for(var grant:mapper.listScopeGrants(scope.tenantId(),scope.id()))if("ACTIVE".equals(grant.status())&&grant.expiresAt().isAfter(Instant.now()))for(String agent:allowed(grant))project(grant,actor.userId(),agent,current.revision());
            } else if("LEAVE".equals(command.action())&&Set.of("ACTIVE","INVITED").contains(member.status())) {
                one(mapper.updateMember(member,"LEFT",b(command.idempotencyKey())));
                for(var projection:mapper.listMemberProjections(scope.tenantId(),scope.id(),member.userId()))revoke(projection);
            } else throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            one(mapper.advanceScope(scope));return memberships.view(actor,memberships.scope(actor.tenantId(),scopeId));
        });
    }
    public GrantView withdrawAgent(IdentityFacade.Subject original,String id,RevisionCommand command) {
        var actor=memberships.current(original);return memberships.transaction.execute(tx->{var grant=withdraw(actor,id,command);if(grant.scopeId()!=null)throw failure("MEMORY_SCOPE_DENIED");return agentView(grant);});
    }
    public ShareView withdrawShare(IdentityFacade.Subject original,String id,RevisionCommand command) {
        var actor=memberships.current(original);return memberships.transaction.execute(tx->{var grant=withdraw(actor,id,command);if(grant.scopeId()==null)throw failure("MEMORY_SCOPE_DENIED");return shareView(grant);});
    }
    private GrantPO withdraw(IdentityFacade.Subject actor,String id,RevisionCommand command) {
        id(command.idempotencyKey());var grant=grant(actor.tenantId(),id);
        if(!Arrays.equals(grant.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");
        if("REVOKED".equals(grant.status()))return grant;
        if(grant.revision()!=command.expectedRevision())throw failure("MEMORY_SHARING_REVISION_CONFLICT");
        one(mapper.updateGrant(grant,"REVOKED"));for(var projection:mapper.listGrantProjections(grant.tenantId(),grant.id()))revoke(projection);return grant(actor.tenantId(),id);
    }
    private void project(GrantPO grant,String user,String target,long memberRevision) {
        var value=source(text(grant.tenantId()),text(grant.ownerId()),grant.originAgent(),text(grant.itemId()),text(grant.versionId()),grant.itemRevision());
        policy(text(grant.tenantId()),user,target,grant.fieldKey(),value.value());
        var row=new ProjectionPO(grant.tenantId(),uuid(),grant.id(),b(user),target,grant.revision(),memberRevision,"ACTIVE",grant.expiresAt(),null);
        one(mapper.insertProjection(row));one(mapper.insertProjectionSource(row));
    }
    private void revoke(ProjectionPO projection) {
        if(!"ACTIVE".equals(projection.state()))return;
        one(mapper.revokeProjection(projection));one(mapper.revokeProjectionSource(projection));
        var source=packets.findSource(projection.tenantId(),projection.id());
        memories.advanceTombstone(projection.tenantId(),"SOURCE",projection.id(),source.deletionEpoch(),source.grantEpoch(),source.sourceEpoch());
        one(memories.insertOutbox(projection.tenantId(),uuid(),projection.id(),b(Long.toString(projection.grantRevision())),"MEMORY_SHARE_REVOKED",source.deletionEpoch()));
    }
    public record Projected(MemoryContextPacket.Item item,Instant expiresAt) { }
    public List<Projected> select(IdentityFacade.Subject original,MemoryScopeDTO target,Set<String> fields) {
        if(!enabled())return List.of();var actor=memberships.current(original);
        if(!actor.tenantId().equals(target.tenantId())||!actor.userId().equals(target.userId())||!com.aiep.aihub.api.memory.MemorySharingContracts.AGENTS.contains(target.domain()))throw failure("MEMORY_SCOPE_DENIED");
        var result=new ArrayList<Projected>();for(var projection:mapper.listReadable(b(target.tenantId()),b(target.userId()),target.domain())) {
            try {var value=hydrate(actor,target,projection);if(fields.contains(value.item().fieldKey()))result.add(value);}
            catch(com.aiep.aihub.api.memory.MemoryContracts.MemoryException denied){if(!Set.of("MEMORY_SOURCE_CHANGED","MEMORY_SCOPE_DENIED","FEATURE_DISABLED").contains(denied.code()))throw denied;}
        }
        // 多scope/私有值矛盾不选最新；共享候选同字段不同值全部不注入。
        var values=new HashMap<String,Set<String>>();for(var item:result)values.computeIfAbsent(item.item().fieldKey(),unused->new HashSet<>()).add(item.item().value());
        return result.stream().filter(item->values.get(item.item().fieldKey()).size()==1).limit(3).toList();
    }
    public Projected hydrate(IdentityFacade.Subject original,MemoryScopeDTO target,String projectionId) {
        var actor=memberships.current(original);var projection=mapper.lockProjection(b(target.tenantId()),b(projectionId));if(projection==null)throw failure("MEMORY_SOURCE_CHANGED");return hydrate(actor,target,projection);
    }
    private Projected hydrate(IdentityFacade.Subject actor,MemoryScopeDTO target,ProjectionPO projection) {
        if(!target.tenantId().equals(actor.tenantId())||!Arrays.equals(projection.userId(),b(actor.userId()))||!target.userId().equals(actor.userId())||!target.domain().equals(projection.targetAgent())||!"ACTIVE".equals(projection.state())||!projection.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SOURCE_CHANGED");
        var grant=grant(target.tenantId(),text(projection.grantId()));
        if(!"ACTIVE".equals(grant.status())||grant.revision()!=projection.grantRevision()||!allowed(grant).contains(target.domain()))throw failure("MEMORY_SOURCE_CHANGED");
        if(grant.scopeId()!=null){var scope=memberships.scope(target.tenantId(),text(grant.scopeId()));var member=memberships.requireMember(actor,scope);if(member.revision()!=projection.memberRevision())throw failure("MEMORY_SOURCE_CHANGED");}
        else if(!Arrays.equals(grant.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");
        var value=source(target.tenantId(),text(grant.ownerId()),grant.originAgent(),text(grant.itemId()),text(grant.versionId()),grant.itemRevision());policy(target.tenantId(),target.userId(),target.domain(),grant.fieldKey(),value.value());
        var source=packets.findSource(grant.tenantId(),projection.id());if(source==null||source.blocked()||!"MEMORY_SHARE_GRANT".equals(source.sourceType()))throw failure("MEMORY_SOURCE_CHANGED");
        var all=new ArrayList<>(value.dependencies());all.add(new Dependency("MEMORY_SHARE_GRANT",text(projection.id()),Long.toString(grant.revision()),source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch()));
        var closure=MemoryPacketDigest.dependencies(all);dependencies.requireCurrent(target,closure);
        return new Projected(new MemoryContextPacket.Item("share:"+text(projection.id()),text(grant.versionId()),grant.fieldKey(),value.value(),closure),projection.expiresAt());
    }
    private GrantPO grant(String tenant,String id){var row=mapper.lockGrant(b(tenant),b(id));if(row==null)throw failure("MEMORY_NOT_FOUND");return row;}
    private List<String> allowed(GrantPO row){try{return JSON.readValue(row.allowedAgentsJson(),new TypeReference<List<String>>(){});}catch(java.io.IOException error){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    private GrantView agentView(GrantPO row){return new GrantView(text(row.id()),text(row.itemId()),text(row.versionId()),row.fieldKey(),row.originAgent(),allowed(row).get(0),row.revision(),row.status(),row.expiresAt(),"NOT_REQUESTED");}
    private ShareView shareView(GrantPO row){return new ShareView(text(row.id()),row.scopeId()==null?null:text(row.scopeId()),text(row.itemId()),text(row.versionId()),row.fieldKey(),row.originAgent(),allowed(row),text(row.ownerId()),row.revision(),row.status(),row.expiresAt(),"NOT_REQUESTED");}
    private static String json(Object value){try{return JSON.writeValueAsString(value);}catch(java.io.IOException error){throw failure("MEMORY_SHARING_INVALID");}}
    private static String fingerprint(Object... values){return MemoryPacketDigest.canonicalDigest(JSON.valueToTree(values));}
}
