package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.api.memory.MemoryProposalContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.repository.memory.MemoryProposalMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 有限候选持久状态机；确认只复用原偏好权威事务，不读取预算、不触发索引或模型。 */
@Service
public class MemoryProposalService {
    boolean enabled(){return enabled;}
    private static final ObjectMapper JSON=new ObjectMapper();
    private final boolean enabled;
    private final MemoryProposalMapper mapper;
    private final MemoryMapper memories;
    private final MemoryPacketMapper packets;
    private final MemorySummarySourceService sources;
    private final MemoryScopePolicy scopes;
    private final MemorySessionBindingService bindings;
    private final MemoryPolicyService policies;
    private final MemoryPreferenceService preferences;
    private final MemoryConflictService conflicts;
    private final MemoryDependencyService dependencies;
    private final MemoryValueCodec codec;
    private final TransactionTemplate transaction;
    public MemoryProposalService(@Value("${aiep.memory.proposals-enabled:false}") boolean enabled,
            MemoryProposalMapper mapper,MemoryMapper memories,MemoryPacketMapper packets,MemorySummarySourceService sources,
            MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryPolicyService policies,
            MemoryPreferenceService preferences,MemoryConflictService conflicts,MemoryDependencyService dependencies,
            MemoryValueCodec codec,PlatformTransactionManager manager) {
        this.enabled=enabled;this.mapper=mapper;this.memories=memories;this.packets=packets;this.sources=sources;
        this.scopes=scopes;this.bindings=bindings;this.policies=policies;this.preferences=preferences;
        this.conflicts=conflicts;this.dependencies=dependencies;this.codec=codec;transaction=new TransactionTemplate(manager);
        transaction.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    private void authorize(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        if(!enabled)throw failure("FEATURE_DISABLED");
        if(scope==null||!"CONVERSATION".equals(scope.sessionKind())||"hr".equals(scope.domain()))throw failure("MEMORY_SCOPE_DENIED");
        scopes.require(actor,scope,Set.of());bindings.require(actor,scope);codec.currentVersion();
    }
    private record Policy(byte[] id,byte[] version,long retention,Set<String> sourceTypes) { }
    private Policy policy(MemoryScopeDTO scope) {
        var published=sources.mapper.lockPublishedPolicy(b(scope.tenantId()),scope.domain());
        MemoryPolicyService.requireArtifactPolicy(published);
        try {
            var config=JSON.readTree(published.policyJson()).path("proposals");
            if(!config.path("enabled").isBoolean()||!config.path("enabled").booleanValue()
                    ||!config.path("sourceTypes").isArray()||!config.path("retentionSeconds").isIntegralNumber())throw failure("FEATURE_DISABLED");
            long retention=config.path("retentionSeconds").longValue();var types=new HashSet<String>();
            for(var type:config.path("sourceTypes")) {
                if(!type.isTextual()||!Set.of("MESSAGE","CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION").contains(type.textValue()))throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");
                types.add(type.textValue());
            }
            if(retention<1||retention>15552000||types.isEmpty())throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");
            return new Policy(published.id(),published.versionId(),retention,Set.copyOf(types));
        }catch(java.io.IOException invalid){throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");}
    }
    /** 每task仅一个批次，每直接source版本仅归属一个批次；CPU录入不创建任何derive运行。 */
    public BatchResult submit(IdentityFacade.Subject actor,Submission command) {
        if(command==null)throw failure("MEMORY_PROPOSAL_INVALID");authorize(actor,command.scope());
        try{return transaction.execute(tx->submitTransaction(actor,command));}
        catch(DuplicateKeyException race){throw failure("MEMORY_PROPOSAL_REVISION_CONFLICT");}
    }
    private BatchResult submitTransaction(IdentityFacade.Subject actor,Submission command) {
        var scope=command.scope();var policy=policy(scope);
        var anchor=sources.original(actor,scope,command.executionId());
        String fingerprint=HexFormat.of().formatHex(codec.hmac(b(scope.tenantId()),"proposal-submission/1",json(command),text(policy.version())));
        var old=mapper.lockBatch(b(scope.tenantId()),anchor.taskId());
        if(old!=null) {
            if(!fingerprint.equals(old.fingerprint())||!Arrays.equals(old.userId(),b(scope.userId())))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
            return new BatchResult(text(anchor.taskId()),mapper.listBatch(old.tenantId(),old.taskId()).stream().map(row->project(scope,refresh(scope,row))).toList(),read(old.actionsJson(),new TypeReference<List<Action>>(){}));
        }
        var frozen=freezeSources(scope,command.sourceMessageIds(),policy);
        var closure=frozen.dependencies();
        var items=new TreeMap<String,MemoryItemPO>();
        for(var candidate:command.candidates()) {
            var fieldPolicy=policies.require(scope,candidate.fieldKey(),candidate.value());
            if(!Arrays.equals(fieldPolicy.id(),policy.id())||!Arrays.equals(fieldPolicy.versionId(),policy.version()))throw failure("MEMORY_PROPOSAL_STALE");
            items.put(candidate.fieldKey(),null);
        }
        // 先按固定字段顺序锁稳定逻辑锚，多个候选不会各建随机ACTIVE记录。
        for(String field:List.copyOf(items.keySet())) {
            var item=new MemoryItemPO(b(scope.tenantId()),uuid(),"USER",b(scope.userId()),b(scope.userId()),scope.domain(),scope.topLevelAgentId(),"USER_PRIVATE",MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()),"assistant_response",field,"LIVE",0,null,0,0,0);
            mapper.ensureItem(item);item=memories.findPreferenceItem(item.tenantId(),item.subjectId(),item.domain(),item.fieldKey());
            if(item==null)throw failure("MEMORY_STORAGE_UNAVAILABLE");
            item=memories.findItemForUpdate(item.tenantId(),item.id());requireItem(scope,item);
            if(suppressed(scope,field)||!"LIVE".equals(item.lifecycle()))throw failure("MEMORY_PROPOSAL_SUPPRESSED");items.put(field,item);
        }
        one(mapper.insertBatch(new BatchPO(b(scope.tenantId()),anchor.taskId(),b(command.executionId()),b(scope.userId()),scope.domain(),b(scope.sessionId()),b(command.idempotencyKey()),fingerprint,policy.id(),policy.version(),"[]")));
        for(var direct:frozen.directSources())one(mapper.claimSource(b(scope.tenantId()),anchor.taskId(),b(direct.sourceId()),b(direct.sourceVersion())));
        var results=new ArrayList<Proposal>();var actions=new ArrayList<Action>();
        for(var candidate:command.candidates()) {
            var item=items.get(candidate.fieldKey());var current=item.currentVersionId()==null?null:memories.findPreferenceVersion(item.tenantId(),item.id(),item.currentVersionId());
            if(item.currentVersionId()!=null&&current==null)throw failure("MEMORY_SOURCE_CHANGED");
            byte[] valueHash=codec.hmac(item.tenantId(),"value",candidate.value());
            var pending=new ArrayList<>(mapper.pendingValues(item.tenantId(),item.id()));
            if(pending.stream().anyMatch(hash->MessageDigest.isEqual(hash,valueHash))){actions.add(Action.NOOP);continue;}
            for(var competing:command.candidates())if(competing.fieldKey().equals(candidate.fieldKey())&&!competing.value().equals(candidate.value()))pending.add(codec.hmac(item.tenantId(),"value",competing.value()));
            var action=conflicts.classify(valueHash,current==null?null:current.contentHmac(),pending);actions.add(action);
            if(action==Action.NOOP)continue;
            byte[] id=uuid();var sealed=codec.seal(item.tenantId(),b("proposal:"+text(item.id())),id,candidate.value());
            var row=new ProposalPO(item.tenantId(),id,item.id(),anchor.taskId(),b(command.executionId()),b(scope.userId()),scope.domain(),scope.topLevelAgentId(),b(scope.sessionId()),candidate.fieldKey(),action.name(),"PENDING",0,item.revision(),policy.id(),policy.version(),frozen.expiresAt(),json(command.sourceMessageIds()),json(closure),sealed.keyVersion(),sealed.payload(),sealed.nonce(),sealed.tag(),sealed.hmac(),null,null,null,0,0,null);
            one(mapper.insertProposal(row));
            for(var dependency:closure)one(packets.insertDependency(row.tenantId(),b(dependency.sourceId()),"PROPOSAL",id,id,null,dependency.grantEpoch(),dependency.sourceEpoch(),dependency.deletionEpoch()));
            results.add(project(scope,row));
        }
        one(mapper.setBatchActions(b(scope.tenantId()),anchor.taskId(),json(actions)));
        return new BatchResult(text(anchor.taskId()),results,actions);
    }
    private record Frozen(List<Dependency> directSources,List<Dependency> dependencies,Instant expiresAt) { }
    private Frozen freezeSources(MemoryScopeDTO scope,List<String> messageIds,Policy policy) {
        var all=new ArrayList<Dependency>();var direct=new ArrayList<Dependency>();Instant expires=Instant.now().plusSeconds(policy.retention());
        var ordered=messageIds.stream().sorted((a,c)->Arrays.compareUnsigned(b(a),b(c))).toList();
        for(String id:ordered) {
            var message=sources.message(scope,id);var group=sources.group(scope,message);
            if(!messageIds.containsAll(group.stream().map(m->text(m.id())).toList()))throw failure("MEMORY_PROPOSAL_GROUP_INCOMPLETE");
            var inherited=dependencies.dependencies(scope,"MESSAGE",id,"user".equalsIgnoreCase(message.role())?message.contentHash():"1");
            if(inherited.isEmpty())throw failure("MEMORY_PROPOSAL_SOURCE_REQUIRED");
            requireSources(scope,inherited,policy);Instant deadline=dependencies.requireCurrent(scope,inherited);
            if(deadline.isBefore(expires))expires=deadline;
            var state=packets.findSource(b(scope.tenantId()),message.id());
            if(state==null){one(sources.mapper.insertMessageSource(b(scope.tenantId()),message.id(),b(message.contentHash()),expires));state=packets.findSource(b(scope.tenantId()),message.id());}
            if(state==null||state.blocked()||!"MESSAGE".equals(state.sourceType())||!Arrays.equals(state.sourceVersion(),b(message.contentHash())))throw failure("MEMORY_SOURCE_CHANGED");
            var own=new Dependency("MESSAGE",id,message.contentHash(),state.grantEpoch(),state.sourceEpoch(),state.deletionEpoch());
            direct.add(own);all.add(own);all.addAll(inherited);
        }
        var closure=MemoryPacketDigest.dependencies(all);if(closure.size()>512)throw failure("MEMORY_PROPOSAL_SOURCE_LIMIT");
        requireSources(scope,closure,policy);var deadline=dependencies.requireCurrent(scope,closure);if(deadline.isBefore(expires))expires=deadline;
        return new Frozen(List.copyOf(direct),closure,expires);
    }
    private void requireSources(MemoryScopeDTO scope,List<Dependency> closure,Policy policy) {
        if(closure.isEmpty()||closure.size()>512||closure.stream().anyMatch(d->!policy.sourceTypes().contains(d.sourceType())))throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");
        dependencies.requireCurrent(scope,closure);sources.requireInputMessages(scope,closure);
        for(var source:closure)if("USER_PREFERENCE_DECISION".equals(source.sourceType())) {
            var basis=sources.mapper.findBasis(b(scope.tenantId()),b(source.sourceId()));
            if(basis==null||!Arrays.equals(basis.ownerId(),b(scope.userId()))||!Arrays.equals(basis.actorId(),b(scope.userId()))
                    ||!scope.domain().equals(basis.domain())||!scope.topLevelAgentId().equals(basis.originTopAgentId())
                    ||!Arrays.equals(basis.currentVersionId(),basis.versionId())||!Arrays.equals(basis.versionId(),b(source.sourceVersion())))throw failure("MEMORY_SOURCE_CHANGED");
        }
    }
    public List<Proposal> list(IdentityFacade.Subject actor,MemoryScopeDTO scope,int limit) {
        authorize(actor,scope);if(limit<1||limit>100)throw failure("MEMORY_PROPOSAL_INVALID");
        return transaction.execute(tx->mapper.listOwned(b(scope.tenantId()),b(scope.userId()),scope.domain(),b(scope.sessionId()),limit).stream().map(row->project(scope,refresh(scope,row))).toList());
    }
    public Proposal get(IdentityFacade.Subject actor,MemoryScopeDTO scope,String id) {
        authorize(actor,scope);b(id);return transaction.execute(tx->project(scope,refresh(scope,owned(scope,mapper.readProposal(b(scope.tenantId()),b(id))))));
    }
    /** 原execution已过期不影响有权用户的CPU决策；不得在此读取原预算或启动模型/Embedding。 */
    public Proposal decide(IdentityFacade.Subject actor,String id,DecisionCommand command) {
        if(command==null)throw failure("MEMORY_PROPOSAL_INVALID");authorize(actor,command.scope());b(id);
        return transaction.execute(tx->{
            var scope=command.scope();var row=owned(scope,mapper.readProposal(b(scope.tenantId()),b(id)));
            row=refresh(scope,row);var item=memories.findItemForUpdate(row.tenantId(),row.itemId());requireItem(scope,item);
            row=owned(scope,mapper.lockProposal(row.tenantId(),row.id()));
            if(row.decisionRequestId()!=null) {
                if(!Arrays.equals(row.decisionRequestId(),b(command.idempotencyKey()))||!Arrays.equals(row.decisionActorId(),b(actor.userId()))
                        ||!command.action().name().equals(row.decisionAction())||row.decisionExpectedRevision()!=command.expectedProposalRevision()
                        ||row.decisionExpectedItemRevision()!=command.expectedItemRevision())throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
                return project(scope,row);
            }
            if(!"PENDING".equals(row.status()))return project(scope,row);
            if(row.revision()!=command.expectedProposalRevision()||item.revision()!=command.expectedItemRevision()
                    ||row.expectedItemRevision()!=command.expectedItemRevision())throw failure("MEMORY_PROPOSAL_REVISION_CONFLICT");
            String value=open(row);String next;byte[] version=null;
            if(command.action()==Decision.CONFIRM) {
                var preferenceCommand=new PreferenceCommand(scope,row.fieldKey(),value,item.revision(),command.idempotencyKey(),null);
                var preference=item.currentVersionId()==null?preferences.save(actor,preferenceCommand):preferences.correct(actor,text(item.id()),preferenceCommand);
                version=b(preference.versionId());
                // 用户确认成为权威根，原派生来源仍保留完整安全边，撤权不能借确认洗掉血缘。
                for(var source:closure(row))one(packets.insertDependency(row.tenantId(),b(source.sourceId()),"MEMORY_VERSION",row.itemId(),version,null,source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch()));
                next="ACCEPTED";
            } else {
                if(memories.findPreferenceDecision(row.tenantId(),b(command.idempotencyKey()))!=null)throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
                byte[] decision=uuid();one(memories.insertPreferenceDecision(new DecisionPO(row.tenantId(),decision,item.id(),null,b(actor.userId()),"PROPOSAL_REJECT",b(command.idempotencyKey()),item.revision(),item.revision())));next="REJECTED";
            }
            one(mapper.resolve(row,next,b(command.idempotencyKey()),b(actor.userId()),command.action().name(),command.expectedItemRevision(),version));
            return project(scope,mapper.lockProposal(row.tenantId(),row.id()));
        });
    }
    private ProposalPO refresh(MemoryScopeDTO scope,ProposalPO input) {
        owned(scope,input);String invalid=null;
        if(suppressed(scope,input.fieldKey()))invalid="SUPPRESSED";
        else if(input.expiresAt()==null||!input.expiresAt().isAfter(Instant.now()))invalid="EXPIRED";
        else if(input.encryptedPayload()!=null)try {
            var policy=policy(scope);if(!Arrays.equals(policy.id(),input.policyId())||!Arrays.equals(policy.version(),input.policyVersionId()))throw failure("MEMORY_PROPOSAL_STALE");
            requireSources(scope,closure(input),policy);policies.require(scope,input.fieldKey(),open(input));
        }catch(MemoryException sourceChanged) {
            if(Set.of("MEMORY_KEY_UNAVAILABLE","MEMORY_STORAGE_UNAVAILABLE").contains(sourceChanged.code()))throw sourceChanged;
            invalid="STALE";
        }
        if(invalid!=null&&input.encryptedPayload()!=null) {
            one(mapper.invalidate(input,invalid));return owned(scope,mapper.lockProposal(input.tenantId(),input.id()));
        }
        return input;
    }
    private boolean suppressed(MemoryScopeDTO scope,String field) {return memories.countPreferenceSuppression(b(scope.tenantId()),b(scope.userId()),scope.domain(),MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()),field)>0;}
    private Proposal project(MemoryScopeDTO scope,ProposalPO row) {
        owned(scope,row);String value=row.encryptedPayload()==null?null:open(row);
        return new Proposal(text(row.id()),text(row.itemId()),scope,row.fieldKey(),value,Action.valueOf(row.action()),Status.valueOf(row.status()),row.revision(),row.expectedItemRevision(),row.expiresAt(),"NOT_REQUESTED",row.acceptedVersionId()==null?null:text(row.acceptedVersionId()),closure(row));
    }
    private String open(ProposalPO row){return codec.openSealed(row.tenantId(),b("proposal:"+text(row.itemId())),row.id(),new MemoryValueCodec.Sealed(row.encryptedPayload(),row.nonce(),row.authTag(),row.contentHmac(),row.keyVersion()));}
    private List<Dependency> closure(ProposalPO row){return read(row.dependenciesJson(),new TypeReference<List<Dependency>>(){});}
    private ProposalPO owned(MemoryScopeDTO scope,ProposalPO row) {
        if(row==null||!Arrays.equals(row.tenantId(),b(scope.tenantId()))||!Arrays.equals(row.userId(),b(scope.userId()))||!scope.domain().equals(row.domain())
                ||!scope.topLevelAgentId().equals(row.topLevelAgentId())||!Arrays.equals(row.sessionId(),b(scope.sessionId())))throw failure("MEMORY_NOT_FOUND");return row;
    }
    private void requireItem(MemoryScopeDTO scope,MemoryItemPO item) {
        if(item==null||!Arrays.equals(item.tenantId(),b(scope.tenantId()))||!Arrays.equals(item.subjectId(),b(scope.userId()))||!Arrays.equals(item.ownerId(),b(scope.userId()))
                ||!scope.domain().equals(item.domain())||!scope.topLevelAgentId().equals(item.originTopAgentId())||!"USER_PRIVATE".equals(item.scopeType())
                ||!Arrays.equals(item.scopeId(),MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()))||!"assistant_response".equals(item.purpose()))throw failure("MEMORY_SCOPE_DENIED");
    }
    private static <T>T read(String value,TypeReference<T> type){try{return JSON.readValue(value,type);}catch(Exception failure){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    private static String json(Object value){try{return JSON.writeValueAsString(value);}catch(Exception failure){throw failure("MEMORY_PROPOSAL_INVALID");}}
    private static MemoryException failure(String code){return new MemoryException(code);}
    private static void one(int count){if(count!=1)throw failure("MEMORY_PROPOSAL_REVISION_CONFLICT");}
    private static byte[] b(String value){return MemoryMapper.identity(value);}
    private static byte[] uuid(){return b(UUID.randomUUID().toString());}
    private static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
}
