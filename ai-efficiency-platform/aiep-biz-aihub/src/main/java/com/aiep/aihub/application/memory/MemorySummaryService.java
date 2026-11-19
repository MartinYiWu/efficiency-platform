package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.aihub.application.memory.MemorySummarySourceService.*;
import com.aiep.aihub.repository.memory.MemorySummaryMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.aiep.platformai.api.dto.MemoryHistoryMessage;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.aiep.aihub.application.memory.MemorySummarySourceService.*;

/** 摘要存储提交与当前来源读取；COMMITTED不授予模型注入、费用或自由文本质量保证。 */
@Service
public class MemorySummaryService {
    private static final ObjectMapper SUMMARY_JSON=JSON.copy().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    private final MemorySummarySourceService sources;
    public MemorySummaryService(MemorySummarySourceService sources){this.sources=sources;}
    public boolean enabled(){return sources.enabled();}
    public record CommittedSegmentView(String segmentId,long firstSequence,long lastSequence,long expiresAt,int sourceCount,String freeTextQuality) {}
    public record CommittedSummary(SummarySegment segment,List<SummaryInputSource> sources,List<SummaryBasisEvent> basisEvents,
            long sourceRevision,String authorityRef,String commitRef,String status,boolean authorized,
            List<com.aiep.platformai.api.dto.MemoryContextPacket.Dependency> currentDependencies,String retentionRef,long expiresAt,
            com.aiep.platformai.api.dto.MemoryContextPacket.Dependency summaryDependency,List<String> coveredMessageIds) {
        public CommittedSummary {sources=List.copyOf(sources);basisEvents=List.copyOf(basisEvents);currentDependencies=List.copyOf(currentDependencies);coveredMessageIds=List.copyOf(coveredMessageIds);}
        @Override public String toString(){return "CommittedSummary[redacted]";}
    }
    record CommitResult(SummarySegment segment,String error) {}

    /** 内部服务提交；调用方不得据此绕过后续原Agent基线收益/计窗门禁。 */
    public SummarySegment commitSegment(IdentityFacade.Subject actor,MemoryScopeDTO scope,String planId,SummarySegment candidate) {
        sources.authorize(actor,scope);b(planId);
        if(candidate==null||!candidate.scope().equals(neutral(scope)))throw failure("SUMMARY_SCOPE_MISMATCH");
        var outcome=sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);sources.requireScope(scope,wm);
            if(wm.deletionEpoch()!=0)throw failure("SUMMARY_STALE");
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));
            if(plan==null||Set.of("SCRUBBED","STALE").contains(plan.state()))throw failure("SUMMARY_STALE");
            sources.checkOriginal(scope,plan.originalSessionRef(),plan.originalDeadline());
            if(!Arrays.equals(plan.originalSessionRef(),b(actor.sessionRef())))throw failure("MEMORY_IDENTITY_REQUIRED");
            var frozen=sources.openPlan(plan);
            try {sources.revalidate(scope,key,plan,frozen);}
            catch(MemoryException invalid) {
                if("FROZEN".equals(plan.state()))one(sources.mapper.finishPlan(b(scope.tenantId()),key,b(planId),"STALE"));
                return new CommitResult(null,"SUMMARY_STALE");
            }
            if(frozen.requiredEntries().isEmpty())throw failure("SUMMARY_SOURCE_PROJECTION_REQUIRED");
            new MemorySummaryPolicy().validateSegment(candidate,frozen.sources(),frozen.events(),sources.now(),frozen.sourceRevision());
            requireEntries(candidate,frozen);
            if(candidate.expiresAt()>frozen.expiresAt())throw failure("SUMMARY_EXPIRY_EXTENDED");
            String digest=segmentDigest(candidate);
            var previous=sources.mapper.findPlanSegment(b(scope.tenantId()),key,b(planId));
            if(previous!=null) {
                if(!"COMMITTED".equals(previous.state())||!Arrays.equals(previous.id(),b(candidate.segmentId()))||!digest.equals(previous.payloadDigest()))throw failure("MEMORY_IDEMPOTENCY_CONFLICT");
                return new CommitResult(candidate,null);
            }
            if(!"FROZEN".equals(plan.state())||wm.commitRevision()!=plan.commitRevision()||candidate.watermark().firstSequence()<=wm.coveredThrough())throw failure("MEMORY_REVISION_CONFLICT");
            var sealed=sources.codec.seal(b(scope.tenantId()),b("summary-segment:"+key),b(candidate.segmentId()),json(candidate));
            one(sources.mapper.insertSegment(new SegmentPO(b(scope.tenantId()),key,b(candidate.segmentId()),b(planId),candidate.watermark().firstSequence(),candidate.watermark().lastSequence(),wm.commitRevision()+1,
                candidate.expiresAt(),digest,sealed.keyVersion(),sealed.payload(),sealed.nonce(),sealed.tag(),sealed.hmac(),"COMMITTED")));
            one(sources.mapper.insertSummarySource(b(scope.tenantId()),b(candidate.segmentId()),b(digest),java.time.Instant.ofEpochSecond(candidate.expiresAt())));
            var deps=new ArrayList<>(candidate.sourceDependencies());
            deps.add(summaryDependency(scope,candidate.segmentId(),digest));
            var closure=MemoryPacketDigest.dependencies(deps);
            sources.dependencies.record(scope,"SUMMARY",candidate.segmentId(),digest,text(plan.executionId()),closure,List.of(closure),List.of());
            one(sources.mapper.commitWatermark(wm,candidate.watermark().lastSequence(),plan.commitRevision()));
            one(sources.mapper.finishPlan(b(scope.tenantId()),key,b(planId),"COMMITTED"));return new CommitResult(candidate,null);
        });
        if(outcome.error()!=null)throw failure(outcome.error());return outcome.segment();
    }
    private static void requireEntries(SummarySegment candidate,FrozenSources frozen) {
        var entries=new ArrayList<SummaryEntry>();entries.add(candidate.goal());entries.addAll(candidate.confirmedConstraints());entries.addAll(candidate.decisions());entries.addAll(candidate.openQuestions());entries.addAll(candidate.importantRefs());entries.addAll(candidate.uncertainties());
        for(var required:frozen.requiredEntries()) {
            boolean present=entries.stream().anyMatch(actual->actual.claimRef().equals(required.claimRef())&&actual.contentOrigin()==required.contentOrigin()
                &&actual.decisionStatus()==required.decisionStatus()&&actual.sourceRefs().equals(required.sourceRefs())&&Objects.equals(actual.basisEventRef(),required.basisEventRef())&&actual.criticalValues().equals(required.criticalValues()));
            if(!present)throw failure("SUMMARY_REQUIRED_STATE_CHANGED");
        }
    }
    /** 只读当前合法摘要；不建水位/计划、不生成，也不回退旧段。 */
    public SummarySegment readCommitted(IdentityFacade.Subject actor,MemoryScopeDTO scope,String segmentId) {
        sources.authorize(actor,scope);b(segmentId);
        return sources.transactions.execute(tx->readCurrent(scope,sources.scopeKey(scope),segmentId));
    }
    SummarySegment readCurrent(MemoryScopeDTO scope,String key,String segmentId) {
        var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);if(wm==null)throw failure("MEMORY_NOT_FOUND");sources.requireScope(scope,wm);
        if(wm.deletionEpoch()!=0)throw failure("MEMORY_NOT_FOUND");
        var segment=sources.mapper.findSegment(b(scope.tenantId()),key,b(segmentId));
        if(segment==null||!"COMMITTED".equals(segment.state())||segment.expiresAt()<=sources.now())throw failure("MEMORY_NOT_FOUND");
        var plan=sources.mapper.findPlan(b(scope.tenantId()),key,segment.planId());
        if(plan==null||!"COMMITTED".equals(plan.state()))throw failure("MEMORY_NOT_FOUND");
        var frozen=sources.openPlan(plan);sources.revalidate(scope,key,plan,frozen);
        summaryDependency(scope,segmentId,segment.payloadDigest());
        String body=sources.codec.openSealed(b(scope.tenantId()),b("summary-segment:"+key),segment.id(),new MemoryValueCodec.Sealed(segment.encryptedPayload(),segment.nonce(),segment.authTag(),segment.contentHmac(),segment.keyVersion()));
        var result=read(body,new TypeReference<SummarySegment>(){});
        if(!result.scope().equals(neutral(scope))||!segmentDigest(result).equals(segment.payloadDigest()))throw failure("MEMORY_NOT_FOUND");
        new MemorySummaryPolicy().validateSegment(result,frozen.sources(),frozen.events(),sources.now(),frozen.sourceRevision());requireEntries(result,frozen);return result;
    }
    public List<CommittedSegmentView> listCommitted(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        if(!enabled())return List.of();sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(wm==null||wm.deletionEpoch()!=0)return List.of();sources.requireScope(scope,wm);
            var result=new ArrayList<CommittedSegmentView>();
            for(var row:sources.mapper.listSegments(b(scope.tenantId()),key)) {
                try {
                    var current=readCurrent(scope,key,text(row.id()));result.add(new CommittedSegmentView(current.segmentId(),current.watermark().firstSequence(),current.watermark().lastSequence(),current.expiresAt(),current.coveredSources().size(),"UNVERIFIED"));
                }catch(MemoryException unavailable) {
                    if(!Set.of("MEMORY_NOT_FOUND","SUMMARY_STALE","MEMORY_SOURCE_CHANGED","SUMMARY_SOURCE_EXPIRED","SUMMARY_SOURCE_INCOMPLETE","SUMMARY_BASIS_UNKNOWN").contains(unavailable.code()))throw unavailable;
                }
            }
            return List.copyOf(result);
        });
    }
    /** 只供当前已鉴权的运行装配读取；权威来自真实selfsource及完整闭包，非模型自报type。 */
    public List<CommittedSummary> exportCommitted(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        if(!enabled())return List.of();sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(wm==null||wm.deletionEpoch()!=0)return List.of();sources.requireScope(scope,wm);
            var result=new ArrayList<CommittedSummary>();
            for(var row:sources.mapper.listSegments(b(scope.tenantId()),key)) {
                try {result.add(exportOne(scope,key,row));}
                catch(MemoryException unavailable) {
                    if(!Set.of("MEMORY_NOT_FOUND","SUMMARY_STALE","MEMORY_SOURCE_CHANGED","SUMMARY_SOURCE_EXPIRED","SUMMARY_SOURCE_INCOMPLETE","SUMMARY_BASIS_UNKNOWN").contains(unavailable.code()))throw unavailable;
                }
            }
            return List.copyOf(result);
        });
    }
    private CommittedSummary exportOne(MemoryScopeDTO scope,String key,SegmentPO row) {
        if(row==null)throw failure("MEMORY_NOT_FOUND");var segment=readCurrent(scope,key,text(row.id()));
        var plan=sources.mapper.findPlan(b(scope.tenantId()),key,row.planId());var frozen=sources.openPlan(plan);
        var self=summaryDependency(scope,segment.segmentId(),row.payloadDigest());var all=new ArrayList<>(segment.sourceDependencies());all.add(self);
        var closure=MemoryPacketDigest.dependencies(all);sources.dependencies.requireCurrent(scope,closure);
        return new CommittedSummary(segment,frozen.sources(),frozen.events(),frozen.sourceRevision(),text(plan.id()),segment.segmentId(),"COMMITTED",true,closure,text(plan.policyVersionId()),segment.expiresAt(),self,
            segment.coveredSources().stream().map(d->d.sourceId()).toList());
    }
    public static String segmentDigest(SummarySegment segment){return MemoryPacketDigest.canonicalDigest(SUMMARY_JSON.valueToTree(segment));}
    record DeriveTemplateSource(SummaryInputSource metadata,String body,String bodySha256) {
        @Override public String toString(){return "DeriveTemplateSource[redacted]";}
    }
    record DeriveTemplateBody(String contractVersion,String planId,String operationId,String executionId,String taskId,
            long deadlineEpochSeconds,com.aiep.platformai.api.dto.MemoryRuntimeManifest.Scope scope,String mode,List<DeriveTemplateSource> sources,
            List<SummaryBasisEvent> events,List<SummaryEntry> requiredEntries,long sessionRevision,long sourceRevision,String authorityRef) {
        @Override public String toString(){return "DeriveTemplate[redacted]";}
    }
    /** 仅原submit插packet/ANCHOR后调用；没有可信required就返回null，不创建运行或费用授权。 */
    public String bootstrapDeriveTemplate(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,String planId,List<String> historyIds) {
        if(!enabled()||scope==null||!"CONVERSATION".equals(scope.sessionKind())||!Set.of("operations","customer-service").contains(scope.domain())
                ||historyIds==null||historyIds.isEmpty()||historyIds.size()>128||new HashSet<>(historyIds).size()!=historyIds.size())return null;
        sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            if(!deriveTemplatePolicy(scope))return null;
            try {
                for(String id:historyIds) {
                    var message=sources.message(scope,id);var members=sources.group(scope,message).stream().map(m->text(m.id())).toList();
                    int start=historyIds.indexOf(members.getFirst());
                    if(start<0||start+members.size()>historyIds.size()||!historyIds.subList(start,start+members.size()).equals(members))return null;
                }
            }catch(MemoryException incomplete) {
                if(Set.of("SUMMARY_SOURCE_INCOMPLETE","SUMMARY_GROUP_INCOMPLETE","SUMMARY_STALE","MEMORY_SOURCE_CHANGED").contains(incomplete.code()))return null;
                throw incomplete;
            }
            var plan=sources.freeze(actor,scope,executionId,planId,historyIds);
            if(plan.frozen().mode()!=DeriveMode.PROPOSALS&&plan.frozen().requiredEntries().isEmpty())return null;
            return deriveTemplate(scope,plan);
        });
    }
    /** restore只读原plan，不把后来source追加到旧execution，也不临时补建计划。 */
    public String rebuildDeriveTemplate(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,String planId) {
        if(!enabled())return null;sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            if(!deriveTemplatePolicy(scope))throw failure("SUMMARY_PURPOSE_DENIED");
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(wm==null||wm.deletionEpoch()!=0)throw failure("MEMORY_SOURCE_CHANGED");sources.requireScope(scope,wm);
            var row=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));
            if(row==null||!Set.of("FROZEN","COMMITTED").contains(row.state())||!Arrays.equals(row.executionId(),b(executionId))
                    ||!Arrays.equals(row.originalSessionRef(),b(actor.sessionRef())))throw failure("MEMORY_SOURCE_CHANGED");
            sources.checkOriginal(scope,row.originalSessionRef(),row.originalDeadline());
            var frozen=sources.openPlan(row);var current=sources.revalidate(scope,key,row,frozen);
            if(frozen.mode()!=DeriveMode.PROPOSALS&&frozen.requiredEntries().isEmpty())return null;
            return deriveTemplate(scope,new FrozenPlan(planId,executionId,text(row.taskId()),row.originalDeadline(),frozen,current.bodies()));
        });
    }
    private boolean deriveTemplatePolicy(MemoryScopeDTO scope) {
        try {sources.policy(scope);}
        catch(MemoryException disabled){if(Set.of("FEATURE_DISABLED","SUMMARY_PURPOSE_DENIED").contains(disabled.code()))return false;throw disabled;}
        var policy=sources.mapper.lockPublishedPolicy(b(scope.tenantId()),scope.domain());
        var maximum=tree(policy.policyJson()).path("context").path("summary").path("maxPaidOperations");
        return maximum.isIntegralNumber()&&maximum.canConvertToInt()&&maximum.intValue()==1;
    }
    private static String deriveTemplate(MemoryScopeDTO scope,FrozenPlan plan) {
        var frozen=plan.frozen();var values=new ArrayList<DeriveTemplateSource>();
        for(int index=0;index<frozen.sources().size();index++) {
            String body=plan.bodies().get(index);values.add(new DeriveTemplateSource(frozen.sources().get(index),body,com.aiep.platformai.api.dto.MemoryDeriveRequest.sha256(body)));
        }
        String node=scope.domain().equals("operations")?"direct":"customer-service:answer_general";
        var execution=new com.aiep.platformai.api.dto.MemoryRuntimeManifest.Scope(neutral(scope),plan.taskId(),plan.executionId(),node,"assistant_response",scope.topLevelAgentId());
        return canonicalSummaryJson(new DeriveTemplateBody("memory-derive-template/1",plan.planId(),plan.planId(),plan.executionId(),plan.taskId(),plan.originalDeadline(),execution,frozen.mode().name(),
            values,frozen.events(),frozen.requiredEntries(),frozen.sessionRevision(),frozen.sourceRevision(),plan.planId()));
    }
    public record ContextProjection(String json,List<Dependency> dependencies,long expiresAt,String referenceJson) {
        public ContextProjection {dependencies=List.copyOf(dependencies);}
        @Override public String toString(){return "SummaryContextProjection[redacted]";}
    }
    record OriginalMessageSnapshot(String messageId,String role,String contentSha256,List<Dependency> safetyDependencies,boolean groupCompleted) {}
    record HistoryReference(String messageId,String role,String contentSha256) {}
    record ProjectionReferences(String contractVersion,List<String> segmentIds,List<HistoryReference> history,String payloadSha256) {}
    record ContextBody(String contractVersion,com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope scope,List<OriginalMessageSnapshot> originalMessages,List<CommittedSummary> summaries) {}
    record RegisteredHistory(List<OriginalMessageSnapshot> messages,List<Dependency> dependencies,long expiresAt) {}

    /** 仅提交路径装配当前真实history；半组/来源不匹配返回null，普通原文路径不被误标压缩。 */
    public ContextProjection contextProjection(IdentityFacade.Subject actor,MemoryScopeDTO scope,List<MemoryHistoryMessage> history) {
        if(!enabled()||scope==null||!Set.of("operations","customer-service").contains(scope.domain())||!"CONVERSATION".equals(scope.sessionKind())||history==null||history.isEmpty())return null;
        sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            if(!projectionPolicy(scope)||!historyComplete(scope,history))return null;
            var committed=exportCommitted(actor,scope);
            var registered=registerHistory(scope,history,true);
            return assembleProjection(scope,registered,committed);
        });
    }
    /** refs-only恢复只读取原白名单；新提交段或原文改变不能混入旧execution。 */
    public ContextProjection rebuildProjection(IdentityFacade.Subject actor,MemoryScopeDTO scope,String referenceJson) {
        sources.authorize(actor,scope);
        return sources.transactions.execute(tx->{
            if(!projectionPolicy(scope))throw failure("SUMMARY_PURPOSE_DENIED");
            ProjectionReferences refs;
            try {refs=SUMMARY_JSON.readValue(referenceJson,ProjectionReferences.class);}
            catch(java.io.IOException invalid){throw failure("MEMORY_SOURCE_CHANGED");}
            if(!"memory-summary-context-refs/1".equals(refs.contractVersion())||refs.segmentIds()==null||refs.segmentIds().size()>32
                    ||new HashSet<>(refs.segmentIds()).size()!=refs.segmentIds().size()||refs.history()==null||refs.history().isEmpty()||refs.history().size()>128
                    ||refs.payloadSha256()==null||!refs.payloadSha256().matches("[0-9a-f]{64}"))throw failure("MEMORY_SOURCE_CHANGED");
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(wm==null||wm.deletionEpoch()!=0)throw failure("MEMORY_SOURCE_CHANGED");sources.requireScope(scope,wm);
            var history=new ArrayList<MemoryHistoryMessage>();
            for(var ref:refs.history()) {
                var message=sources.message(scope,ref.messageId());
                if(!message.role().equalsIgnoreCase(ref.role())||!message.contentHash().equals(ref.contentSha256()))throw failure("MEMORY_SOURCE_CHANGED");
                String version=ref.role().equals("user")?message.contentHash():"1";
                history.add(new MemoryHistoryMessage(ref.messageId(),version,ref.role(),message.body(),sources.dependencies.dependencies(scope,"MESSAGE",ref.messageId(),version)));
            }
            if(!historyComplete(scope,history))throw failure("MEMORY_SOURCE_CHANGED");
            var committed=new ArrayList<CommittedSummary>();
            for(String segmentId:refs.segmentIds())committed.add(exportOne(scope,key,sources.mapper.findSegment(b(scope.tenantId()),key,b(segmentId))));
            var result=assembleProjection(scope,registerHistory(scope,history,false),committed);
            if(!refs.payloadSha256().equals(MemoryPacketDigest.canonicalDigest(tree(result.json()))))throw failure("MEMORY_SOURCE_CHANGED");
            return result;
        });
    }
    private boolean projectionPolicy(MemoryScopeDTO scope) {
        if(!Set.of("operations","customer-service").contains(scope.domain()))return false;
        try {sources.policy(scope);}
        catch(MemoryException denied){if(Set.of("FEATURE_DISABLED","SUMMARY_PURPOSE_DENIED").contains(denied.code()))return false;throw denied;}
        var policy=sources.mapper.lockPublishedPolicy(b(scope.tenantId()),scope.domain());var types=tree(policy.policyJson()).path("context").path("sourceTypes");
        var allowed=new HashSet<String>();types.forEach(t->allowed.add(t.asText()));return allowed.containsAll(Set.of("MESSAGE","SUMMARY"));
    }
    private boolean historyComplete(MemoryScopeDTO scope,List<MemoryHistoryMessage> history) {
        if(history.size()>128||history.stream().map(MemoryHistoryMessage::messageId).distinct().count()!=history.size())return false;
        var ids=history.stream().map(MemoryHistoryMessage::messageId).toList();
        try {
            for(var original:history) {
                var message=sources.message(scope,original.messageId());
                if(!original.role().equalsIgnoreCase(message.role())||!original.content().equals(message.body())
                        ||!original.version().equals(original.role().equals("user")?message.contentHash():"1"))return false;
                var group=sources.group(scope,message);var members=group.stream().map(m->text(m.id())).toList();
                int start=ids.indexOf(members.getFirst());
                if(start<0||start+members.size()>ids.size()||!ids.subList(start,start+members.size()).equals(members))return false;
                var actual=sources.dependencies.dependencies(scope,"MESSAGE",original.messageId(),original.version());
                if(actual.isEmpty()||!original.safetyDependencies().containsAll(actual))return false;
                for(var declared:original.safetyDependencies())if(!actual.contains(declared)) {
                    if(!declared.sourceType().equals("MESSAGE")||!declared.sourceId().equals(original.messageId())||!declared.sourceVersion().equals(message.contentHash()))return false;
                    var state=sources.packets.findSource(b(scope.tenantId()),b(original.messageId()));
                    if(state==null||state.blocked()||!state.sourceType().equals("MESSAGE")||state.grantEpoch()!=declared.grantEpoch()||state.sourceEpoch()!=declared.sourceEpoch()||state.deletionEpoch()!=declared.deletionEpoch())return false;
                }
                if(actual.stream().anyMatch(d->!Set.of("CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION","MESSAGE").contains(d.sourceType())))return false;
            }
            return true;
        }catch(MemoryException incomplete) {
            if(Set.of("SUMMARY_SOURCE_INCOMPLETE","SUMMARY_GROUP_INCOMPLETE","SUMMARY_STALE","MEMORY_SOURCE_CHANGED").contains(incomplete.code()))return false;
            throw incomplete;
        }
    }
    private RegisteredHistory registerHistory(MemoryScopeDTO scope,List<MemoryHistoryMessage> history,boolean allowRegistration) {
        String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
        if(wm==null&&allowRegistration)wm=sources.ensureWatermark(scope,key);sources.requireScope(scope,wm);
        if(wm.deletionEpoch()!=0)throw failure("MEMORY_SOURCE_CHANGED");var policy=sources.policy(scope);
        var inherited=MemoryPacketDigest.dependencies(history.stream().flatMap(h->sources.dependencies.dependencies(scope,"MESSAGE",h.messageId(),h.version()).stream()).toList());
        sources.dependencies.requireCurrent(scope,inherited);sources.lockBasisItems(scope,inherited);sources.requireInputMessages(scope,inherited);
        for(var original:history) {
            var message=sources.message(scope,original.messageId());var group=sources.group(scope,message);
            var row=sources.mapper.findSource(b(scope.tenantId()),key,b(original.messageId()));
            if(row==null) {
                if(!allowRegistration)throw failure("MEMORY_SOURCE_CHANGED");
                sources.register(scope,key,wm,message,group.stream().map(m->text(m.id())).toList(),policy);wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            }else sources.checkSourceRow(row,message,group.stream().map(m->text(m.id())).toList(),policy);
        }
        long expires=Long.MAX_VALUE;var snapshots=new ArrayList<OriginalMessageSnapshot>();var dependencies=new ArrayList<Dependency>();
        for(var original:history) {
            var message=sources.message(scope,original.messageId());var row=sources.mapper.findSource(b(scope.tenantId()),key,message.id());
            var projected=sources.project(scope,row,sources.group(scope,message));
            if(!projected.sourceDependencies().containsAll(original.safetyDependencies()))throw failure("MEMORY_SOURCE_CHANGED");
            snapshots.add(new OriginalMessageSnapshot(original.messageId(),original.role(),message.contentHash(),projected.sourceDependencies(),true));
            dependencies.addAll(projected.sourceDependencies());expires=Math.min(expires,projected.expiresAt());
        }
        return new RegisteredHistory(List.copyOf(snapshots),MemoryPacketDigest.dependencies(dependencies),expires);
    }
    private ContextProjection assembleProjection(MemoryScopeDTO scope,RegisteredHistory history,List<CommittedSummary> committed) {
        var all=new ArrayList<>(history.dependencies());long expires=history.expiresAt();
        for(var summary:committed){all.addAll(summary.currentDependencies());expires=Math.min(expires,summary.expiresAt());}
        var body=new ContextBody("memory-summary-context/1",neutral(scope),history.messages(),List.copyOf(committed));
        String payload=canonicalSummaryJson(body);String digest=MemoryPacketDigest.canonicalDigest(tree(payload));
        var references=new ProjectionReferences("memory-summary-context-refs/1",committed.stream().map(s->s.segment().segmentId()).toList(),
            history.messages().stream().map(m->new HistoryReference(m.messageId(),m.role(),m.contentSha256())).toList(),digest);
        return new ContextProjection(payload,MemoryPacketDigest.dependencies(all),expires,canonicalSummaryJson(references));
    }
    private static String canonicalSummaryJson(Object value) {
        try {return SUMMARY_JSON.writeValueAsString(sortedSummaryJson(SUMMARY_JSON.valueToTree(value)));}
        catch(java.io.IOException invalid){throw failure("MEMORY_STORAGE_UNAVAILABLE");}
    }
    private static Object sortedSummaryJson(JsonNode value) {
        if(value.isObject()){var result=new TreeMap<String,Object>();value.fields().forEachRemaining(e->result.put(e.getKey(),sortedSummaryJson(e.getValue())));return result;}
        if(value.isArray()){var result=new ArrayList<Object>();value.forEach(v->result.add(sortedSummaryJson(v)));return result;}return value;
    }
    private com.aiep.platformai.api.dto.MemoryContextPacket.Dependency summaryDependency(MemoryScopeDTO scope,String id,String digest) {
        var state=sources.packets.findSource(b(scope.tenantId()),b(id));
        if(state==null||!"SUMMARY".equals(state.sourceType())||!Arrays.equals(state.sourceVersion(),b(digest)))throw failure("MEMORY_NOT_FOUND");
        var dependency=new com.aiep.platformai.api.dto.MemoryContextPacket.Dependency("SUMMARY",id,digest,state.grantEpoch(),state.sourceEpoch(),state.deletionEpoch());
        sources.dependencies.requireCurrent(scope,List.of(dependency));return dependency;
    }
    /** 本slice无Agent摘要注入；仅本库完整擦除，不能充当外部thread清理ACK。 */
    public void forget(IdentityFacade.Subject actor,MemoryScopeDTO scope) {
        sources.authorize(actor,scope);sources.transactions.executeWithoutResult(tx->{
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(wm==null)return;sources.requireScope(scope,wm);if(wm.deletionEpoch()!=0)return;
            for(var summary:sources.mapper.listSummarySourceIds(b(scope.tenantId()),key)) {
                sources.mapper.revokeSummarySource(b(scope.tenantId()),summary.sourceId());
                var state=sources.packets.findSource(b(scope.tenantId()),summary.sourceId());
                if(state!=null)sources.memories.advanceTombstone(b(scope.tenantId()),"SOURCE",summary.sourceId(),state.deletionEpoch(),state.grantEpoch(),state.sourceEpoch());
            }
            sources.mapper.revokeMessageSources(b(scope.tenantId()),key);sources.mapper.tombstoneMessageSources(b(scope.tenantId()),key);
            sources.mapper.scrubSegments(b(scope.tenantId()),key);sources.mapper.scrubPlans(b(scope.tenantId()),key);
            one(sources.mapper.forgetWatermark(wm));
        });
    }
}
