package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemorySharingContracts.*;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemorySharingMapper;
import com.aiep.aihub.repository.memory.MemorySharingMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 本域ACL仅管理记忆分享；部门事实来自当前Identity，不复用岗位/候选人范围。 */
@Service
public class MemoryScopeMembershipService {
    final MemorySharingMapper mapper;final TransactionTemplate transaction;
    private final boolean enabled;private final IdentityFacade identity;
    public MemoryScopeMembershipService(@Value("${aiep.memory.sharing-enabled:false}") boolean enabled,
            MemorySharingMapper mapper,IdentityFacade identity,PlatformTransactionManager manager) {
        this.enabled=enabled;this.mapper=mapper;this.identity=identity;transaction=new TransactionTemplate(manager);
        transaction.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    public boolean enabled(){return enabled;}
    IdentityFacade.Subject current(IdentityFacade.Subject actor) {
        if(!enabled)throw failure("FEATURE_DISABLED");
        if(actor==null||actor.sessionRef()==null)throw failure("MEMORY_IDENTITY_REQUIRED");
        var now=identity.refresh(actor.tenantId(),actor.userId(),actor.sessionRef()).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
        if(!actor.tenantId().equals(now.tenantId())||!actor.userId().equals(now.userId())||!actor.sessionRef().equals(now.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");return now;
    }
    public ScopeView create(IdentityFacade.Subject original,ScopeCommand command) {
        var actor=current(original);id(command.approverUserId());id(command.idempotencyKey());
        if(!Set.of("PROJECT","DEPARTMENT","ORGANIZATION").contains(command.scopeType())||actor.userId().equals(command.approverUserId())
                ||command.expiresAt()==null||!command.expiresAt().isAfter(Instant.now())||command.expiresAt().isAfter(Instant.now().plusSeconds(15552000)))throw failure("MEMORY_SHARING_INVALID");
        if("DEPARTMENT".equals(command.scopeType())){id(command.departmentId());if(!actor.departmentIds().contains(command.departmentId()))throw failure("MEMORY_SCOPE_DENIED");}
        else if(command.departmentId()!=null)throw failure("MEMORY_SHARING_INVALID");
        if("ORGANIZATION".equals(command.scopeType())&&!actor.permissions().contains("memory:share:organization"))throw failure("MEMORY_SCOPE_DENIED");
        String fingerprint=MemoryPacketDigest.canonicalDigest(new ObjectMapper().findAndRegisterModules().valueToTree(List.of(actor.userId(),command)));
        return transaction.execute(tx->{
            var prior=mapper.findScopeRequest(b(actor.tenantId()),b(command.idempotencyKey()));
            if(prior!=null){if(!fingerprint.equals(prior.fingerprint()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");return view(actor,prior);}
            var row=new ScopePO(b(actor.tenantId()),uuid(),command.scopeType(),command.departmentId()==null?null:b(command.departmentId()),b(actor.userId()),b(command.approverUserId()),"PENDING",0,command.expiresAt(),b(command.idempotencyKey()),fingerprint);
            one(mapper.insertScope(row));one(mapper.insertMember(new MemberPO(row.tenantId(),row.id(),row.ownerId(),"ACTIVE",0,b(command.idempotencyKey()))));return view(actor,row);
        });
    }
    public ScopeView approve(IdentityFacade.Subject original,String scopeId,RevisionCommand command) {
        var actor=current(original);id(command.idempotencyKey());return transaction.execute(tx->{
            var row=scope(actor.tenantId(),scopeId);requireApprover(actor,row);
            if(!"PENDING".equals(row.status())||row.revision()!=command.expectedRevision())throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            one(mapper.approveScope(row));return view(actor,scope(actor.tenantId(),scopeId));
        });
    }
    public List<ScopeView> list(IdentityFacade.Subject original) {
        var actor=current(original);return transaction.execute(tx->mapper.listScopes(b(actor.tenantId()),b(actor.userId())).stream().map(row->view(actor,row)).toList());
    }
    public ScopeView invite(IdentityFacade.Subject original,String scopeId,MemberCommand command) {
        var actor=current(original);id(command.userId());id(command.idempotencyKey());return transaction.execute(tx->{
            var row=scope(actor.tenantId(),scopeId);requireOwner(actor,row);requireActive(row);
            if(row.revision()!=command.expectedRevision())throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            if(mapper.lockMember(row.tenantId(),row.id(),b(command.userId()))!=null)throw failure("MEMORY_SHARING_REVISION_CONFLICT");
            if(mapper.listMembers(row.tenantId(),row.id()).size()>=100)throw failure("MEMORY_SHARING_MEMBER_LIMIT");
            one(mapper.insertMember(new MemberPO(row.tenantId(),row.id(),b(command.userId()),"INVITED",0,b(command.idempotencyKey()))));one(mapper.advanceScope(row));return view(actor,scope(actor.tenantId(),scopeId));
        });
    }
    ScopePO scope(String tenant,String id){var row=mapper.lockScope(b(tenant),b(id));if(row==null)throw failure("MEMORY_NOT_FOUND");return row;}
    void requireActive(ScopePO scope){if(!"ACTIVE".equals(scope.status())||!scope.expiresAt().isAfter(Instant.now()))throw failure("MEMORY_SCOPE_DENIED");}
    void requireOwner(IdentityFacade.Subject actor,ScopePO scope){if(!Arrays.equals(scope.ownerId(),b(actor.userId())))throw failure("MEMORY_SCOPE_DENIED");requireDepartment(actor,scope);}
    void requireApprover(IdentityFacade.Subject actor,ScopePO scope){if(!Arrays.equals(scope.approverId(),b(actor.userId()))||!actor.permissions().contains("memory:share:approve"))throw failure("MEMORY_SCOPE_DENIED");requireDepartment(actor,scope);}
    void requireDepartment(IdentityFacade.Subject actor,ScopePO scope){if(scope.departmentId()!=null&&!actor.departmentIds().contains(text(scope.departmentId())))throw failure("MEMORY_SCOPE_DENIED");if("ORGANIZATION".equals(scope.scopeType())&&!actor.permissions().contains("memory:share:organization"))throw failure("MEMORY_SCOPE_DENIED");}
    MemberPO requireMember(IdentityFacade.Subject actor,ScopePO scope){requireActive(scope);requireDepartment(actor,scope);var member=mapper.lockMember(scope.tenantId(),scope.id(),b(actor.userId()));if(member==null||!"ACTIVE".equals(member.status()))throw failure("MEMORY_SCOPE_DENIED");return member;}
    ScopeView view(IdentityFacade.Subject actor,ScopePO row){var member=mapper.lockMember(row.tenantId(),row.id(),b(actor.userId()));return new ScopeView(text(row.id()),row.scopeType(),row.departmentId()==null?null:text(row.departmentId()),text(row.ownerId()),text(row.approverId()),row.revision(),row.status(),member==null?null:member.status(),member==null?0:member.revision(),row.expiresAt());}
    static MemoryException failure(String code){return new MemoryException(code);}static void one(int count){if(count!=1)throw failure("MEMORY_SHARING_REVISION_CONFLICT");}
    static byte[] b(String value){return MemoryMapper.identity(value);}static void id(String value){b(value);}static byte[] uuid(){return b(UUID.randomUUID().toString());}static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
}
