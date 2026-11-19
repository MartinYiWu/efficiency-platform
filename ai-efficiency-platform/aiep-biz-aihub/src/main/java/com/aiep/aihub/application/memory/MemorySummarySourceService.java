package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemorySummaryMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 真实会话来源冻结；无模型/HTTP，不把消息角色或模型标签解释成确认事件。 */
@Service
public class MemorySummarySourceService {
    static final ObjectMapper JSON=new ObjectMapper();
    private final boolean enabled;
    final MemorySummaryMapper mapper;
    final MemoryMapper memories;
    final MemoryPacketMapper packets;
    final MemoryDependencyService dependencies;
    final MemoryValueCodec codec;
    final MemoryScopePolicy scopes;
    final MemorySessionBindingService bindings;
    final IdentityFacade identity;
    final TransactionTemplate transactions;
    final Clock clock;
    @Autowired public MemorySummarySourceService(@Value("${aiep.memory.summary-persistence-enabled:false}") boolean enabled,
            MemorySummaryMapper mapper,MemoryMapper memories,MemoryPacketMapper packets,MemoryDependencyService dependencies,
            MemoryValueCodec codec,MemoryScopePolicy scopes,MemorySessionBindingService bindings,IdentityFacade identity,
            PlatformTransactionManager manager) {
        this(enabled,mapper,memories,packets,dependencies,codec,scopes,bindings,identity,manager,Clock.systemUTC());
    }
    public MemorySummarySourceService(boolean enabled,MemorySummaryMapper mapper,MemoryMapper memories,MemoryPacketMapper packets,
            MemoryDependencyService dependencies,MemoryValueCodec codec,MemoryScopePolicy scopes,MemorySessionBindingService bindings,
            IdentityFacade identity,PlatformTransactionManager manager,Clock clock) {
        this.enabled=enabled;this.mapper=mapper;this.memories=memories;this.packets=packets;this.dependencies=dependencies;
        this.codec=codec;this.scopes=scopes;this.bindings=bindings;this.identity=identity;this.transactions=new TransactionTemplate(manager);this.clock=clock;
        this.transactions.setIsolationLevel(org.springframework.transaction.TransactionDefinition.ISOLATION_READ_COMMITTED);
    }
    public boolean enabled(){return enabled;}
    void authorize(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        if(!enabled)throw failure("FEATURE_DISABLED");
        if(scope==null||!"CONVERSATION".equals(scope.sessionKind())||!Set.of("operations","customer-service").contains(scope.domain()))throw failure("SUMMARY_SCOPE_MISMATCH");
        scopes.require(actor,scope,Set.of());codec.currentVersion();
        var owner=scope.domain().equals("operations")?memories.findOperationOwner(b(scope.tenantId()),b(scope.userId()),b(scope.sessionId()))
            :memories.findCustomerServiceOwner(b(scope.tenantId()),b(scope.userId()),b(scope.sessionId()));
        if(owner==null||!Arrays.equals(owner.tenantId(),b(scope.tenantId()))||!Arrays.equals(owner.userId(),b(scope.userId()))||!Arrays.equals(owner.sessionId(),b(scope.sessionId())))throw failure("SUMMARY_SCOPE_MISMATCH");
    }
    String scopeKey(MemoryScopeDTO scope){return HexFormat.of().formatHex(codec.hmac(b(scope.tenantId()),"summary-scope/1",json(scope)));}
    static Scope neutral(MemoryScopeDTO s){return new Scope(s.tenantId(),s.userId(),s.domain(),s.topLevelAgentId(),s.sessionKind(),s.sessionId());}
    record SummaryPolicyPO(byte[] id,byte[] version,long retentionSeconds,DeriveMode mode,Set<String> proposalSourceTypes) {
        SummaryPolicyPO(byte[] id,byte[] version,long retentionSeconds){this(id,version,retentionSeconds,DeriveMode.SUMMARY,Set.of());}
    }
    SummaryPolicyPO policy(MemoryScopeDTO scope) {
        var row=mapper.lockPublishedPolicy(b(scope.tenantId()),scope.domain());
        MemoryPolicyService.requireArtifactPolicy(row);
        try {
            var root=JSON.readTree(row.policyJson());var node=root.path("context").path("summary");
            if(!node.path("enabled").isBoolean()||!node.path("enabled").booleanValue()||!node.path("purposes").isArray())throw failure("SUMMARY_PURPOSE_DENIED");
            if(node.has("mode")&&!node.path("mode").isTextual())throw failure("SUMMARY_PURPOSE_DENIED");
            DeriveMode mode;try{mode=DeriveMode.valueOf(node.path("mode").asText("SUMMARY"));}catch(IllegalArgumentException invalid){throw failure("SUMMARY_MODE_INVALID");}
            var purposes=JSON.convertValue(node.path("purposes"),new TypeReference<Set<String>>(){});
            var expected=mode==DeriveMode.BOTH?Set.of("SUMMARY","PROPOSALS"):Set.of(mode.name());
            if(!purposes.equals(expected)||!node.path("retentionSeconds").isIntegralNumber())throw failure("SUMMARY_PURPOSE_DENIED");
            long retention=node.path("retentionSeconds").longValue();
            if(retention<1||retention>31536000)throw failure("SUMMARY_PURPOSE_DENIED");
            Set<String> types=Set.of();
            if(mode!=DeriveMode.SUMMARY){
                var proposals=root.path("proposals");
                if(!proposals.path("enabled").isBoolean()||!proposals.path("enabled").booleanValue()||!proposals.path("retentionSeconds").isIntegralNumber()||!proposals.path("sourceTypes").isArray())throw failure("SUMMARY_PURPOSE_DENIED");
                long proposedRetention=proposals.path("retentionSeconds").longValue();types=JSON.convertValue(proposals.path("sourceTypes"),new TypeReference<Set<String>>(){});
                if(proposedRetention<1||proposedRetention>15552000||types.isEmpty()||!Set.of("MESSAGE","CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION").containsAll(types)||"hr".equals(scope.domain()))throw failure("SUMMARY_PURPOSE_DENIED");
                retention=Math.min(retention,proposedRetention);
            }
            return new SummaryPolicyPO(row.id(),row.versionId(),retention,mode,types);
        }catch(java.io.IOException invalid){throw failure("SUMMARY_PURPOSE_DENIED");}
    }
    public record FrozenSources(Scope scope,List<SummaryInputSource> sources,List<SummaryBasisEvent> events,
            List<SummaryEntry> requiredEntries,long sessionRevision,long sourceRevision,long commitRevision,long expiresAt,DeriveMode mode) {
        public FrozenSources {sources=List.copyOf(sources);events=List.copyOf(events);requiredEntries=List.copyOf(requiredEntries);if(mode==null)mode=DeriveMode.SUMMARY;}
        public FrozenSources(Scope scope,List<SummaryInputSource> sources,List<SummaryBasisEvent> events,List<SummaryEntry> requiredEntries,long sessionRevision,long sourceRevision,long commitRevision,long expiresAt){this(scope,sources,events,requiredEntries,sessionRevision,sourceRevision,commitRevision,expiresAt,DeriveMode.SUMMARY);}
        @Override public String toString(){return "FrozenSummarySources[redacted]";}
    }
    public record FrozenPlan(String planId,String executionId,String taskId,long originalDeadline,FrozenSources frozen,List<String> bodies) {
        public FrozenPlan {bodies=List.copyOf(bodies);}
        @Override public String toString(){return "FrozenSummaryPlan[redacted]";}
    }
    /** messageIds顺序就是原调用的明确覆盖顺序；完整run组必须连续，禁止跨范围补取正文。 */
    public FrozenPlan freeze(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,String planId,List<String> messageIds) {
        authorize(actor,scope);b(executionId);b(planId);
        if(messageIds==null||messageIds.isEmpty()||messageIds.size()>128||new HashSet<>(messageIds).size()!=messageIds.size())throw failure("SUMMARY_SOURCES_INVALID");
        messageIds.forEach(MemorySummarySourceService::b);
        return transactions.execute(tx->{
            String key=scopeKey(scope);var wm=ensureWatermark(scope,key);
            var anchor=original(actor,scope,executionId);var policy=policy(scope);
            var old=mapper.findPlan(b(scope.tenantId()),key,b(planId));
            if(old!=null) {
                if(!Arrays.equals(old.executionId(),b(executionId))||!"FROZEN".equals(old.state()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
                var frozen=openPlan(old);
                if(!frozen.sources().stream().map(s->s.sourceRef().sourceId()).toList().equals(messageIds))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
                var checked=revalidate(scope,key,old,frozen);
                return new FrozenPlan(planId,executionId,text(anchor.taskId()),anchor.originalDeadline(),frozen,checked.bodies());
            }
            var sources=new ArrayList<SummaryInputSource>();var bodies=new ArrayList<String>();
            var basisDependencies=new ArrayList<Dependency>();
            for(String id:messageIds) {
                var msg=message(scope,id);
                basisDependencies.addAll(dependencies.dependencies(scope,"MESSAGE",id,"user".equalsIgnoreCase(msg.role())?msg.contentHash():"1"));
            }
            dependencies.requireCurrent(scope,MemoryPacketDigest.dependencies(basisDependencies));
            lockBasisItems(scope,basisDependencies);
            for(String id:messageIds) {
                var msg=message(scope,id);var group=group(scope,msg);
                var members=group.stream().map(m->text(m.id())).toList();
                if(!messageIds.containsAll(members))throw failure("SUMMARY_GROUP_INCOMPLETE");
                register(scope,key,wm,msg,members,policy);wm=mapper.lockWatermark(b(scope.tenantId()),key);
                bodies.add(msg.body());
            }
            for(String id:messageIds) {
                var msg=message(scope,id);sources.add(project(scope,mapper.findSource(b(scope.tenantId()),key,b(id)),group(scope,msg)));
            }
            new MemorySummaryPolicy().admit(policy.mode(),sources,neutral(scope),now());
            var facts=basisFacts(scope,sources);
            sources=withCritical(sources,facts);
            long expires=sources.stream().mapToLong(SummaryInputSource::expiresAt).min().orElseThrow();
            var frozen=new FrozenSources(neutral(scope),sources,facts.events(),facts.entries(),wm.revision(),wm.sourceRevision(),wm.commitRevision(),expires,policy.mode());
            String fingerprint=MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(executionId,text(anchor.taskId()),frozen)));
            var sealed=codec.seal(b(scope.tenantId()),b("summary-plan:"+key),b(planId),json(frozen));
            one(mapper.insertPlan(new PlanPO(b(scope.tenantId()),key,b(planId),b(executionId),anchor.taskId(),anchor.originalSessionRef(),policy.id(),policy.version(),
                wm.revision(),wm.sourceRevision(),wm.commitRevision(),anchor.originalDeadline(),expires,fingerprint,sealed.keyVersion(),sealed.payload(),sealed.nonce(),sealed.tag(),sealed.hmac(),"FROZEN")));
            return new FrozenPlan(planId,executionId,text(anchor.taskId()),anchor.originalDeadline(),frozen,bodies);
        });
    }
    WatermarkPO ensureWatermark(MemoryScopeDTO scope,String key) {
        mapper.ensureWatermark(new WatermarkPO(b(scope.tenantId()),key,b(scope.userId()),scope.domain(),scope.topLevelAgentId(),b(scope.sessionId()),0,0,1,0,0,0));
        var row=mapper.lockWatermark(b(scope.tenantId()),key);requireScope(scope,row);
        if(row.deletionEpoch()!=0)throw failure("MEMORY_SOURCE_CHANGED");return row;
    }
    void requireScope(MemoryScopeDTO scope,WatermarkPO row) {
        if(row==null||!Arrays.equals(row.userId(),b(scope.userId()))||!scope.domain().equals(row.domain())||!scope.topLevelAgentId().equals(row.topLevelAgentId())||!Arrays.equals(row.sessionId(),b(scope.sessionId())))throw failure("SUMMARY_SCOPE_MISMATCH");
    }
    AnchorPO original(IdentityFacade.Subject actor,MemoryScopeDTO scope,String execution) {
        var anchor=mapper.findAnchor(b(scope.tenantId()),b(execution));
        var packet=packets.findPacket(b(scope.tenantId()),b(execution));
        if(anchor==null||packet==null||!Arrays.equals(anchor.userId(),b(scope.userId()))||!Arrays.equals(anchor.originalSessionRef(),b(actor.sessionRef()))
                ||!JSON.valueToTree(scope).equals(tree(packet.scopeJson())))throw failure("SUMMARY_AUTHORITY_BINDING_INVALID");
        checkOriginal(scope,anchor.originalSessionRef(),anchor.originalDeadline());return anchor;
    }
    void checkOriginal(MemoryScopeDTO scope,byte[] session,long deadline) {
        var current=identity.refresh(scope.tenantId(),scope.userId(),text(session)).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
        if(!scope.tenantId().equals(current.tenantId())||!scope.userId().equals(current.userId())||!text(session).equals(current.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");
        if(deadline<=now())throw failure("SUMMARY_SOURCE_EXPIRED");
    }
    MessagePO message(MemoryScopeDTO scope,String id) {
        var row=mapper.lockMessage(b(scope.tenantId()),b(scope.userId()),scope.domain(),b(scope.sessionId()),b(id));
        if(row==null||!row.completed()||row.body()==null||row.body().isBlank())throw failure("SUMMARY_SOURCE_INCOMPLETE");
        return row;
    }
    List<MessagePO> group(MemoryScopeDTO scope,MessagePO msg) {
        var rows=mapper.listGroup(b(scope.tenantId()),b(scope.userId()),scope.domain(),b(scope.sessionId()),msg.runId());
        if(rows==null||rows.isEmpty()||rows.size()>128||rows.stream().anyMatch(r->!r.completed()||r.body()==null||r.body().isBlank()))throw failure("SUMMARY_GROUP_INCOMPLETE");return rows;
    }
    SourcePO register(MemoryScopeDTO scope,String key,WatermarkPO wm,MessagePO message,List<String> members,SummaryPolicyPO policy) {
        var existing=mapper.findSource(b(scope.tenantId()),key,message.id());
        if(existing!=null) {checkSourceRow(existing,message,members,policy);return existing;}
        String version="user".equalsIgnoreCase(message.role())?message.contentHash():"1";
        var inherited=dependencies.dependencies(scope,"MESSAGE",text(message.id()),version);
        if(inherited.isEmpty())throw failure("SUMMARY_DEPENDENCIES_INCOMPLETE");
        requireInputMessages(scope,inherited);
        long expires=Math.min(now()+policy.retentionSeconds(),dependencies.requireCurrent(scope,inherited).getEpochSecond());
        var self=packets.findSource(b(scope.tenantId()),message.id());
        if(self==null) {
            one(mapper.insertMessageSource(b(scope.tenantId()),message.id(),b(message.contentHash()),Instant.ofEpochSecond(expires)));
            self=packets.findSource(b(scope.tenantId()),message.id());
        }
        if(self==null||!"MESSAGE".equals(self.sourceType())||!Arrays.equals(self.sourceVersion(),b(message.contentHash()))||self.retentionDeadline()==null||self.blocked())throw failure("SUMMARY_STALE");
        expires=Math.min(expires,self.retentionDeadline().getEpochSecond());
        var all=new ArrayList<>(inherited);all.add(new Dependency("MESSAGE",text(message.id()),message.contentHash(),self.grantEpoch(),self.sourceEpoch(),self.deletionEpoch()));
        var closure=MemoryPacketDigest.dependencies(all);dependencies.requireCurrent(scope,closure);
        var row=new SourcePO(b(scope.tenantId()),key,message.id(),message.contentHash(),wm.nextSequence(),message.runId(),json(members),json(closure),policy.id(),policy.version(),Instant.ofEpochSecond(expires));
        one(mapper.insertSource(row));one(mapper.advanceSource(wm));return row;
    }
    void checkSourceRow(SourcePO row,MessagePO msg,List<String> members,SummaryPolicyPO policy) {
        if(!row.contentHash().equals(msg.contentHash())||!Arrays.equals(row.groupId(),msg.runId())||!tree(row.groupMembersJson()).equals(JSON.valueToTree(members))
                ||!Arrays.equals(row.policyId(),policy.id())||!Arrays.equals(row.policyVersionId(),policy.version())||row.expiresAt().getEpochSecond()<=now())throw failure("SUMMARY_STALE");
    }
    SummaryInputSource project(MemoryScopeDTO scope,SourcePO row,List<MessagePO> group) {
        var closure=read(row.dependenciesJson(),new TypeReference<List<Dependency>>(){});
        var policy=policy(scope);
        if(policy.mode()!=DeriveMode.SUMMARY)requireProposalInputs(scope,closure,policy);
        long expires=Math.min(row.expiresAt().getEpochSecond(),dependencies.requireCurrent(scope,closure).getEpochSecond());
        var self=closure.stream().filter(d->d.sourceType().equals("MESSAGE")&&d.sourceId().equals(text(row.messageId()))).findFirst().orElseThrow(()->failure("SUMMARY_DEPENDENCIES_INCOMPLETE"));
        var members=new ArrayList<Dependency>();
        for(var msg:group) {
            var state=packets.findSource(b(scope.tenantId()),msg.id());
            if(state==null)throw failure("SUMMARY_GROUP_INCOMPLETE");
            if(!"MESSAGE".equals(state.sourceType())||!Arrays.equals(state.sourceVersion(),b(msg.contentHash())))throw failure("SUMMARY_STALE");
            members.add(new Dependency("MESSAGE",text(msg.id()),msg.contentHash(),state.grantEpoch(),state.sourceEpoch(),state.deletionEpoch()));
        }
        var purposes=policy.mode()==DeriveMode.BOTH?Set.of(SourcePurpose.SUMMARY,SourcePurpose.PROPOSALS):Set.of(SourcePurpose.valueOf(policy.mode().name()));
        return new SummaryInputSource(self,neutral(scope),row.sequenceNo(),text(row.groupId()),members,closure,true,SourceKind.ORIGINAL,purposes,
            policy.mode()==DeriveMode.PROPOSALS?null:row.scopeKey(),policy.mode()==DeriveMode.SUMMARY?null:row.scopeKey(),
            policy.mode()==DeriveMode.PROPOSALS?null:text(row.policyVersionId()),policy.mode()==DeriveMode.SUMMARY?null:text(row.policyVersionId()),expires,List.of());
    }
    private void requireProposalInputs(MemoryScopeDTO scope,List<Dependency> closure,SummaryPolicyPO policy){
        if(closure.isEmpty()||closure.stream().anyMatch(source->!policy.proposalSourceTypes().contains(source.sourceType())))throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");
        requireInputMessages(scope,closure);
        for(var source:closure)if(Set.of("MESSAGE","CURRENT_USER_MESSAGE").contains(source.sourceType())){
            var msg=message(scope,source.sourceId());String body=msg.body();
            if(body==null||body.getBytes(StandardCharsets.UTF_8).length>512||!body.matches("(?iu)(?:[\\s\\p{Punct}，。！？、：（）“”‘’]|请|以后|后续|回答|回复|使用|用|中文|英文|英语|简洁|简短|详细|列表|段落|表格|我|希望|喜欢|一些|一点|好的|好|可以|请你|不要|太长|默认|格式|语言|详细程度|please|use|reply|answer|chinese|english|concise|detailed|list|table|paragraph|format|language|prefer|i|in|yes|ok|okay)+"))throw failure("MEMORY_PROPOSAL_PURPOSE_DENIED");
        }
    }
    record BasisFacts(List<SummaryBasisEvent> events,List<SummaryEntry> entries,Map<String,List<CriticalValue>> criticalByMessage) {}
    void requireInputMessages(MemoryScopeDTO scope,List<Dependency> closure) {
        for(var dep:closure) {
            if("CURRENT_USER_MESSAGE".equals(dep.sourceType())) {
                var source=mapper.lockInputMessage(b(scope.tenantId()),b(scope.userId()),scope.domain(),b(scope.sessionId()),b(dep.sourceId()));
                if(source==null||!source.completed()||!source.contentHash().equals(dep.sourceVersion()))throw failure("SUMMARY_STALE");
            }else if("MESSAGE".equals(dep.sourceType())) {
                var message=message(scope,dep.sourceId());
                if(!message.contentHash().equals(dep.sourceVersion()))throw failure("SUMMARY_STALE");
            }else if(!"USER_PREFERENCE_DECISION".equals(dep.sourceType()))throw failure("SUMMARY_PURPOSE_DENIED");
        }
    }
    void lockBasisItems(MemoryScopeDTO scope,List<Dependency> closure) {
        var ids=new TreeMap<String,byte[]>();
        for(var dep:closure)if("USER_PREFERENCE_DECISION".equals(dep.sourceType())) {
            var basis=mapper.findBasis(b(scope.tenantId()),b(dep.sourceId()));
            if(basis==null)throw failure("SUMMARY_BASIS_UNKNOWN");
            ids.put(HexFormat.of().formatHex(basis.itemId()),basis.itemId());
        }
        // 原forget/invalidation先锁既有source再锁item；更正只创建新source，不反锁旧源。
        for(var id:ids.values())if(memories.findItemForUpdate(b(scope.tenantId()),id)==null)throw failure("SUMMARY_BASIS_UNKNOWN");
    }
    BasisFacts basisFacts(MemoryScopeDTO scope,List<SummaryInputSource> sources) {
        var events=new LinkedHashMap<Dependency,SummaryBasisEvent>();var entries=new ArrayList<SummaryEntry>();var critical=new HashMap<String,List<CriticalValue>>();
        var all=MemoryPacketDigest.dependencies(sources.stream().flatMap(s->s.sourceDependencies().stream()).toList());
        for(var dep:all) {
            if(!"USER_PREFERENCE_DECISION".equals(dep.sourceType()))continue;
            var basis=mapper.findBasis(b(scope.tenantId()),b(dep.sourceId()));
            if(basis==null||!Arrays.equals(basis.actorId(),b(scope.userId()))||!Arrays.equals(basis.ownerId(),b(scope.userId()))||!scope.domain().equals(basis.domain())
                    ||!scope.topLevelAgentId().equals(basis.originTopAgentId())||!Arrays.equals(basis.versionId(),b(dep.sourceVersion())))throw failure("SUMMARY_BASIS_UNKNOWN");
            var currentItem=memories.findItemForUpdate(b(scope.tenantId()),basis.itemId());
            if(currentItem==null||!Arrays.equals(currentItem.currentVersionId(),basis.versionId())||!"LIVE".equals(currentItem.lifecycle())
                    ||currentItem.grantEpoch()!=basis.grantEpoch()||currentItem.sourceEpoch()!=basis.sourceEpoch()||currentItem.deletionEpoch()!=basis.deletionEpoch())throw failure("SUMMARY_BASIS_UNKNOWN");
            var version=memories.findPreferenceVersion(b(scope.tenantId()),basis.itemId(),basis.versionId());
            if(version==null)throw failure("SUMMARY_BASIS_UNKNOWN");
            MemoryPolicyService.requireArtifactPolicy(memories.findPolicyVersion(version.tenantId(),version.policyId(),version.policyVersionId()));
            String value=codec.open(version);String claim="preference:"+text(basis.itemId())+":"+text(basis.versionId());
            var values=List.of(new CriticalValue(basis.fieldKey(),CriticalKind.CONSTRAINT,value,null));
            var refs=sources.stream().filter(s->s.sourceDependencies().contains(dep)).map(SummaryInputSource::sourceRef).toList();
            if(refs.isEmpty())throw failure("SUMMARY_BASIS_SOURCE_MISMATCH");
            events.put(dep,new SummaryBasisEvent(dep,claim,Authority.USER,ContentOrigin.USER_REQUIREMENT,DecisionStatus.CONFIRMED,values,null));
            entries.add(new SummaryEntry(claim,basis.fieldKey()+"="+value,ContentOrigin.USER_REQUIREMENT,DecisionStatus.CONFIRMED,refs,dep,values));
            for(var ref:refs)critical.computeIfAbsent(ref.sourceId(),unused->new ArrayList<>()).addAll(values);
        }
        return new BasisFacts(List.copyOf(events.values()),List.copyOf(entries),critical);
    }
    ArrayList<SummaryInputSource> withCritical(List<SummaryInputSource> sources,BasisFacts facts) {
        var result=new ArrayList<SummaryInputSource>();
        for(var s:sources)result.add(new SummaryInputSource(s.sourceRef(),s.scope(),s.sequence(),s.groupId(),s.groupMembers(),s.sourceDependencies(),s.completed(),s.sourceKind(),s.allowedPurposes(),s.summaryScopeRef(),s.proposalsScopeRef(),s.summaryRetentionRef(),s.proposalsRetentionRef(),s.expiresAt(),facts.criticalByMessage().getOrDefault(s.sourceRef().sourceId(),List.of())));
        return result;
    }
    FrozenSources openPlan(PlanPO row) {
        if("SCRUBBED".equals(row.state()))throw failure("MEMORY_NOT_FOUND");
        return read(codec.openSealed(row.tenantId(),b("summary-plan:"+row.scopeKey()),row.id(),new MemoryValueCodec.Sealed(row.encryptedPayload(),row.nonce(),row.authTag(),row.contentHmac(),row.keyVersion())),new TypeReference<FrozenSources>(){});
    }
    public record Revalidated(FrozenSources frozen,List<String> bodies) {
        @Override public String toString(){return "RevalidatedSummary[redacted]";}
    }
    Revalidated revalidate(MemoryScopeDTO scope,String key,PlanPO plan,FrozenSources frozen) {
        var policy=policy(scope);
        if(!Arrays.equals(policy.id(),plan.policyId())||!Arrays.equals(policy.version(),plan.policyVersionId())||!frozen.scope().equals(neutral(scope))||frozen.mode()!=policy.mode())throw failure("SUMMARY_STALE");
        var frozenDependencies=MemoryPacketDigest.dependencies(frozen.sources().stream().flatMap(s->s.sourceDependencies().stream()).toList());
        dependencies.requireCurrent(scope,frozenDependencies);lockBasisItems(scope,frozenDependencies);
        requireInputMessages(scope,frozenDependencies);
        var current=new ArrayList<SummaryInputSource>();var bodies=new ArrayList<String>();
        for(var original:frozen.sources()) {
            var msg=message(scope,original.sourceRef().sourceId());var members=group(scope,msg);
            var row=mapper.findSource(b(scope.tenantId()),key,msg.id());
            if(row==null)throw failure("SUMMARY_STALE");checkSourceRow(row,msg,members.stream().map(m->text(m.id())).toList(),policy);
            // 每次复验原MESSAGE血缘，不能只查冻结后保存的旧闭包。
            String version="user".equalsIgnoreCase(msg.role())?msg.contentHash():"1";
            var actual=new ArrayList<>(dependencies.dependencies(scope,"MESSAGE",text(msg.id()),version));actual.add(original.sourceRef());
            if(!MemoryPacketDigest.dependencies(actual).equals(MemoryPacketDigest.dependencies(original.sourceDependencies())))throw failure("SUMMARY_STALE");
            current.add(project(scope,row,members));bodies.add(msg.body());
        }
        var facts=basisFacts(scope,current);current=withCritical(current,facts);
        if(!JSON.valueToTree(current).equals(JSON.valueToTree(frozen.sources()))||!JSON.valueToTree(facts.events()).equals(JSON.valueToTree(frozen.events()))
                ||!JSON.valueToTree(facts.entries()).equals(JSON.valueToTree(frozen.requiredEntries())))throw failure("SUMMARY_STALE");
        new MemorySummaryPolicy().admit(frozen.mode(),current,neutral(scope),now());return new Revalidated(frozen,List.copyOf(bodies));
    }
    static String json(Object value){try{return JSON.writeValueAsString(value);}catch(java.io.IOException failure){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static com.fasterxml.jackson.databind.JsonNode tree(String value){try{return JSON.readTree(value);}catch(java.io.IOException failure){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static <T> T read(String value,TypeReference<T> type){try{return JSON.readValue(value,type);}catch(java.io.IOException failure){throw failure("MEMORY_STORAGE_UNAVAILABLE");}}
    static byte[] b(String value){return MemoryMapper.identity(value);}static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
    long now(){return clock.instant().getEpochSecond();}static MemoryException failure(String code){return new MemoryException(code);}static void one(int count){if(count!=1)throw failure("MEMORY_REVISION_CONFLICT");}
}
