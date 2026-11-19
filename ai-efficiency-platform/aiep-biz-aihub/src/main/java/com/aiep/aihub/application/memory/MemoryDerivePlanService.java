package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.aihub.application.memory.MemorySummarySourceService.*;
import com.aiep.aihub.repository.memory.MemorySummaryMapper.PlanPO;
import com.aiep.aihub.repository.operation.OperationRunMapper;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.platformai.api.AiInvocationException;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.core.type.TypeReference;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import static com.aiep.aihub.application.memory.MemorySummarySourceService.*;

/** 原活帧派生的内部编排；不创建RunControl/预算，不提供公共HTTP模板入口。 */
@Service
public class MemoryDerivePlanService {
    private static final ObjectMapper WIRE=JSON.copy().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    private final boolean enabled;
    private final MemorySummarySourceService sources;
    private final MemorySummaryService summaries;
    private final AiInvokeFacade ai;
    private final OperationRunMapper operations;
    private final MemoryProposalService proposals;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.aihub.repository.customer.CustomerServiceMappers customers;
    record KnownPlan(List<String> messages,String state,String fingerprint,String segmentId,DeriveMode mode) {}
    @org.springframework.beans.factory.annotation.Autowired
    public MemoryDerivePlanService(@Value("${aiep.memory.derive-enabled:false}") boolean enabled,
            MemorySummarySourceService sources,MemorySummaryService summaries,AiInvokeFacade ai,
            org.springframework.beans.factory.ObjectProvider<OperationRunMapper> operations,
            org.springframework.beans.factory.ObjectProvider<MemoryProposalService> proposals) {
        this(enabled,sources,summaries,ai,operations.getIfAvailable(),proposals.getIfAvailable());
    }
    public MemoryDerivePlanService(boolean enabled,MemorySummarySourceService sources,MemorySummaryService summaries,
            AiInvokeFacade ai,OperationRunMapper operations) {
        this(enabled,sources,summaries,ai,operations,null);
    }
    public MemoryDerivePlanService(boolean enabled,MemorySummarySourceService sources,MemorySummaryService summaries,
            AiInvokeFacade ai,OperationRunMapper operations,MemoryProposalService proposals) {
        this.enabled=enabled;this.sources=sources;this.summaries=summaries;this.ai=ai;this.operations=operations;this.proposals=proposals;
    }
    /** template只能来自原Agent已登记的冻结帧；未知结果再次传入同一模板，绝不新operation。 */
    public SummarySegment generateAndCommit(IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,String planId,
            List<String> messageIds,MemoryDeriveRequest requestTemplate) {
        if(!enabled||!sources.enabled())throw failure("MEMORY_DERIVE_FEATURE_DISABLED");
        outsideTransaction();
        if(requestTemplate==null)throw failure("DERIVE_ORIGINAL_FRAME_REQUIRED");
        if(!"SUMMARY".equals(requestTemplate.mode())&&(proposals==null||!proposals.enabled()))throw failure("MEMORY_PROPOSAL_FEATURE_DISABLED");
        try {requestTemplate.validateBinding(scope.tenantId());}
        catch(IllegalArgumentException invalid){throw failure("DERIVE_BINDING_CONFLICT");}
        sources.authorize(actor,scope);b(executionId);b(planId);
        if(!Set.of("operations","customer-service").contains(scope.domain()))throw failure("DERIVE_ORIGINAL_FRAME_REQUIRED");
        if(!requestTemplate.planId().equals(planId)||!requestTemplate.authorityRef().equals(planId)
                ||!requestTemplate.executionScope().executionId().equals(executionId)||!requestTemplate.executionScope().conversation().equals(neutral(scope)))throw failure("DERIVE_BINDING_CONFLICT");
        var already=sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var watermark=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(watermark==null)return null;sources.requireScope(scope,watermark);
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));
            if(plan==null||!"COMMITTED".equals(plan.state()))return null;
            if(!Arrays.equals(plan.executionId(),b(executionId))||!Arrays.equals(plan.originalSessionRef(),b(actor.sessionRef()))
                    ||plan.transportFingerprint()==null||!plan.transportFingerprint().equals(requestTemplate.planFingerprint()))throw failure("DERIVE_BINDING_CONFLICT");
            var saved=sources.mapper.findPlanSegment(b(scope.tenantId()),key,b(planId));
            if(saved==null){if(sources.openPlan(plan).mode()!=DeriveMode.SUMMARY)return "";throw failure("MEMORY_NOT_FOUND");}return text(saved.id());
        });
        if(already!=null)return already.isEmpty()?null:summaries.readCommitted(actor,scope,already);
        var frozen=sources.freeze(actor,scope,executionId,planId,messageIds);
        verifyFrozen(requestTemplate,scope,executionId,planId,frozen);
        sources.transactions.executeWithoutResult(tx->{
            String key=sources.scopeKey(scope);var watermark=sources.mapper.lockWatermark(b(scope.tenantId()),key);sources.requireScope(scope,watermark);
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));requirePlan(plan,actor,scope,executionId,requestTemplate);
            requireRuntime(scope,executionId,requestTemplate);var snapshot=sources.openPlan(plan);sources.revalidate(scope,key,plan,snapshot);
            if(plan.transportFingerprint()==null)one(sources.mapper.bindTransportFingerprint(b(scope.tenantId()),key,b(planId),requestTemplate.planFingerprint()));
            else if(!plan.transportFingerprint().equals(requestTemplate.planFingerprint()))throw failure("DERIVE_BINDING_CONFLICT");
        });
        outsideTransaction();
        // transport失败/结果未知不清计划fingerprint；调用者只能沿原ID恢复受信原帧。
        var response=ai.deriveMemory(scope.tenantId(),requestTemplate);
        var proposed="SUMMARY".equals(requestTemplate.mode())?List.<com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate>of():verifyProposals(requestTemplate,response,frozen);
        var candidate="PROPOSALS".equals(requestTemplate.mode())||("BOTH".equals(requestTemplate.mode())&&!"BENEFICIAL".equals(response.benefit().path("status").asText()))?null:verifyResponse(requestTemplate,response,frozen);
        return sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var watermark=sources.mapper.lockWatermark(b(scope.tenantId()),key);sources.requireScope(scope,watermark);
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));requirePlan(plan,actor,scope,executionId,requestTemplate);
            if(!requestTemplate.planFingerprint().equals(plan.transportFingerprint()))throw failure("DERIVE_BINDING_CONFLICT");
            requireRuntime(scope,executionId,requestTemplate);sources.revalidate(scope,key,plan,sources.openPlan(plan));
            if(!proposed.isEmpty()){
                if(proposals==null)throw failure("MEMORY_PROPOSAL_FEATURE_DISABLED");
                proposals.submit(actor,new com.aiep.aihub.api.memory.MemoryProposalContracts.Submission(scope,executionId,messageIds,proposed,planId));
            }
            if(candidate!=null)return summaries.commitSegment(actor,scope,planId,candidate);
            one(sources.mapper.finishPlan(b(scope.tenantId()),key,b(planId),"COMMITTED"));return null;
        });
    }
    /** 正式内部事件只交refs；完整请求从原Agent活帧的只读端口取得。 */
    public SummarySegment handlePendingDerive(OperationActor capturedActor,MemoryScopeDTO scope,String executionId,
            String expectedRuntimeId,String planId,String baselineRef) {
        if(!enabled||!sources.enabled())throw failure("MEMORY_DERIVE_FEATURE_DISABLED");outsideTransaction();
        b(planId);b(baselineRef);b(expectedRuntimeId);
        if(capturedActor.sessionRef()==null)throw failure("MEMORY_IDENTITY_REQUIRED");
        var actor=sources.identity.refresh(capturedActor.tenantId(),capturedActor.userId(),capturedActor.sessionRef()).orElseThrow(()->failure("MEMORY_IDENTITY_REQUIRED"));
        if(!actor.tenantId().equals(capturedActor.tenantId())||!actor.userId().equals(capturedActor.userId())||!capturedActor.sessionRef().equals(actor.sessionRef()))throw failure("MEMORY_IDENTITY_REQUIRED");
        sources.authorize(actor,scope);
        var known=sources.transactions.execute(tx->{
            String key=sources.scopeKey(scope);var watermark=sources.mapper.lockWatermark(b(scope.tenantId()),key);
            if(watermark==null)throw failure("DERIVE_BINDING_CONFLICT");sources.requireScope(scope,watermark);
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));
            if(plan==null||!Arrays.equals(plan.executionId(),b(executionId))||!Arrays.equals(plan.originalSessionRef(),b(actor.sessionRef())))throw failure("DERIVE_BINDING_CONFLICT");
            var segment=sources.mapper.findPlanSegment(b(scope.tenantId()),key,b(planId));
            var frozen="SCRUBBED".equals(plan.state())?null:sources.openPlan(plan);
            return new KnownPlan(frozen==null?List.of():frozen.sources().stream().map(s->s.sourceRef().sourceId()).toList(),
                plan.state(),plan.transportFingerprint(),segment==null?null:text(segment.id()),frozen==null?DeriveMode.SUMMARY:frozen.mode());
        });
        if(known.fingerprint()!=null&&"COMMITTED".equals(known.state())) {
            if(known.segmentId()==null&&known.mode()==DeriveMode.SUMMARY)throw failure("MEMORY_NOT_FOUND");var saved=known.segmentId()==null?null:summaries.readCommitted(actor,scope,known.segmentId());
            ai.finishMemoryDerive(scope.tenantId(),executionId,planId,known.fingerprint(),"COMMITTED");return saved;
        }
        if(known.fingerprint()!=null&&Set.of("STALE","SCRUBBED").contains(known.state())) {
            ai.finishMemoryDerive(scope.tenantId(),executionId,planId,known.fingerprint(),"REJECTED");return null;
        }
        var request=ai.queryMemoryDerivePlan(scope.tenantId(),executionId);
        if(request==null||!request.planId().equals(planId)||!request.baselineRef().equals(baselineRef)||!request.runtimeId().equals(expectedRuntimeId)
                ||!request.executionScope().executionId().equals(executionId)||!request.executionScope().conversation().equals(neutral(scope))||!(scope.domain().equals("operations")?"OPERATIONS":"CUSTOMER_SERVICE").equals(request.runtimeKind()))throw failure("DERIVE_BINDING_CONFLICT");
        try {request.validateBinding(scope.tenantId());}
        catch(IllegalArgumentException invalid){throw failure("DERIVE_BINDING_CONFLICT");}
        SummarySegment result;
        try {
            result=generateAndCommit(actor,scope,executionId,planId,known.messages(),request);
        }catch(MemoryException rejected) {
            if(definiteRejection(rejected.code())) {
                recordRejected(scope,planId,request.planFingerprint());ai.finishMemoryDerive(scope.tenantId(),executionId,planId,request.planFingerprint(),"REJECTED");return null;
            }
            throw rejected;
        }catch(AiInvocationException rejected) {
            if(Set.of(409,422).contains(rejected.status())&&definiteRejection(rejected.code())) {
                recordRejected(scope,planId,request.planFingerprint());ai.finishMemoryDerive(scope.tenantId(),executionId,planId,request.planFingerprint(),"REJECTED");return null;
            }
            throw rejected;
        }
        outsideTransaction();ai.finishMemoryDerive(scope.tenantId(),executionId,planId,request.planFingerprint(),"COMMITTED");return result;
    }
    private void recordRejected(MemoryScopeDTO scope,String planId,String fingerprint) {
        sources.transactions.executeWithoutResult(tx->{
            String key=sources.scopeKey(scope);var wm=sources.mapper.lockWatermark(b(scope.tenantId()),key);sources.requireScope(scope,wm);
            var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));if(plan==null)throw failure("DERIVE_BINDING_CONFLICT");
            if(plan.transportFingerprint()!=null&&!plan.transportFingerprint().equals(fingerprint))throw failure("DERIVE_BINDING_CONFLICT");
            if("FROZEN".equals(plan.state())) {
                if(plan.transportFingerprint()==null)one(sources.mapper.bindTransportFingerprint(b(scope.tenantId()),key,b(planId),fingerprint));
                one(sources.mapper.finishPlan(b(scope.tenantId()),key,b(planId),"STALE"));
            }
        });
    }
    private static boolean definiteRejection(String code) {
        if(Set.of("MEMORY_PROPOSAL_FEATURE_DISABLED","MEMORY_PROPOSAL_PURPOSE_DENIED","MEMORY_PROPOSAL_SUPPRESSED","MEMORY_PROPOSAL_STALE","MEMORY_PROPOSAL_SOURCE_REQUIRED",
                "PROPOSAL_POLICY_DENIED","PROPOSAL_FIELD_DENIED","PROPOSAL_FIELD_SUPPRESSED","PROPOSAL_SOURCE_SUPPRESSED","PROPOSAL_VALUE_DENIED","PROPOSAL_TOKEN_LIMIT","PROPOSAL_COUNT_LIMIT","PROPOSAL_TOKEN_EVIDENCE_REQUIRED").contains(code))return true;
        return Set.of("SUMMARY_STALE","SUMMARY_SCOPE_MISMATCH","SUMMARY_NOT_BENEFICIAL","SUMMARY_SLOT_LIMIT","SUMMARY_PURPOSE_DENIED",
            "SUMMARY_SOURCE_EXPIRED","SUMMARY_SOURCE_INCOMPLETE","SUMMARY_SOURCE_PROJECTION_REQUIRED","SUMMARY_BASIS_UNKNOWN","SUMMARY_REQUIRED_STATE_CHANGED",
            "MEMORY_SOURCE_CHANGED","MEMORY_REVISION_CONFLICT","MEMORY_NOT_FOUND","MEMORY_DERIVE_RESPONSE_INVALID",
            "DERIVE_SCOPE_MISMATCH","DERIVE_BINDING_CONFLICT","DERIVE_SOURCE_BODY_MISMATCH","DERIVE_ORIGINAL_EXECUTION_REQUIRED",
            "DERIVE_ORIGINAL_FRAME_REQUIRED","DERIVE_ORIGINAL_BUDGET_REQUIRED","DERIVE_DEADLINE_EXCEEDED","DERIVE_SCHEMA_REPAIR_EXHAUSTED",
            "CONTEXT_REQUIRED_INPUT_TOO_LARGE","CONTINUATION_AUTH_UNSUPPORTED",
            "SUMMARY_SOURCE_TOKEN_LIMIT","SUMMARY_OUTPUT_TOKEN_LIMIT","SUMMARY_TOKEN_EVIDENCE_REQUIRED","SUMMARY_TOKEN_LIMIT_INVALID",
            "SUMMARY_SOURCES_INVALID","SUMMARY_SOURCES_DUPLICATE","SUMMARY_SOURCE_RANGE_INVALID","SUMMARY_SOURCE_EPOCHS_REQUIRED",
            "SUMMARY_GROUP_INCOMPLETE","SUMMARY_RECURSION_DENIED","SUMMARY_PURPOSE_INCOMPATIBLE","SUMMARY_MODE_INVALID","SUMMARY_TIME_INVALID",
            "SUMMARY_SOURCE_REF_UNKNOWN","SUMMARY_COVERAGE_MISMATCH","SUMMARY_DEPENDENCIES_INCOMPLETE","SUMMARY_WATERMARK_MISMATCH",
            "SUMMARY_EXPIRY_EXTENDED","SUMMARY_BASIS_CLAIM_MISMATCH","SUMMARY_BASIS_SOURCE_MISMATCH","SUMMARY_BASIS_STATUS_MISMATCH",
            "SUMMARY_CLAIM_CONFLICT","SUMMARY_CONFIRMATION_REQUIRED","SUMMARY_CONSTRAINT_UNCONFIRMED","SUMMARY_UNRESOLVED_STATE_CHANGED",
            "SUMMARY_AUTHORITY_REQUIRED","SUMMARY_AUTHORITY_BINDING_INVALID","SUMMARY_REQUIRED_EVENT_MISSING","SUMMARY_CRITICAL_SOURCE_MISMATCH",
            "SUMMARY_CRITICAL_VALUES_CHANGED","SUMMARY_REJECTED_STATUS_INVALID","SUMMARY_REJECTION_REASON_CHANGED","SUMMARY_POLICY_MISMATCH",
            "SUMMARY_BASELINE_MISMATCH","SUMMARY_VALIDATION_FAILED","SUMMARY_VALIDATION_REQUIRED","SUMMARY_VALIDATION_INPUT_INVALID","SUMMARY_REVISION_INVALID").contains(code);
    }
    /** 派生只引用冻结旧来源；从原plan重建完整请求并复算已持久绑定，不继承模型未见的当前输入。 */
    public boolean verifyManifest(MemoryScopeDTO scope,String executionId,String runtimeId,
            com.aiep.aihub.repository.memory.MemoryPacketMapper.PacketRow issued,MemoryRuntimeManifest.Operation operation) {
        if(!enabled||!sources.enabled()||operation.deriveBindingJson()==null||operation.deriveBindingJson().length()>16384
                ||!"memory.derive".equals(operation.nodeId())||operation.operationId()==null)return false;
        return Boolean.TRUE.equals(sources.transactions.execute(tx->{
            try {
                var header=JSON.copy().enable(DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY).readTree(operation.deriveBindingJson());
                var refs=JSON.readTree(issued.referencesJson());var planId=refs.path("derive_plan_id").asText();
                if(planId.isBlank()||!planId.equals(header.path("plan_id").asText())||!planId.equals(header.path("logical_stage_id").asText())
                        ||!operation.operationId().equals(header.path("physical_operation_id").asText())
                        ||header.has("sources")||header.has("events")||header.has("required_entries"))return false;
                String key=sources.scopeKey(scope);var plan=sources.mapper.findPlan(b(scope.tenantId()),key,b(planId));
                if(plan==null||!Set.of("FROZEN","COMMITTED").contains(plan.state())||plan.transportFingerprint()==null
                        ||!plan.transportFingerprint().equals(header.path("plan_fingerprint").asText())
                        ||!Arrays.equals(plan.executionId(),b(executionId))||!Arrays.equals(plan.taskId(),issued.taskId()))return false;
                var frozen=sources.openPlan(plan);var current=sources.revalidate(scope,key,plan,frozen);
                var complete=(com.fasterxml.jackson.databind.node.ObjectNode)header.deepCopy();complete.remove(List.of("logical_stage_id","physical_operation_id"));var sourceNodes=complete.putArray("sources");
                for(int index=0;index<frozen.sources().size();index++) {
                    var node=sourceNodes.addObject();node.set("metadata",WIRE.valueToTree(frozen.sources().get(index)));
                    String body=current.bodies().get(index);node.put("body",body);node.put("body_sha256",MemoryDeriveRequest.sha256(body));
                }
                complete.set("events",WIRE.valueToTree(frozen.events()));complete.set("required_entries",WIRE.valueToTree(frozen.requiredEntries()));
                var request=WIRE.treeToValue(complete,MemoryDeriveRequest.class);request.validateBinding(scope.tenantId());
                if(!request.runtimeId().equals(runtimeId)||!request.runId().equals(runtimeId)||!request.operationId().equals(planId)
                        ||!request.authorityRef().equals(planId)||!request.mode().equals(frozen.mode().name())
                        ||request.deadlineEpochSeconds()>plan.originalDeadline()||request.deadlineEpochSeconds()<=sources.now()
                        ||request.sessionRevision()!=frozen.sessionRevision()||request.sourceRevision()!=frozen.sourceRevision()
                        ||!request.executionScope().equals(operation.scope())||!request.executionScope().conversation().equals(neutral(scope))
                        ||!request.executionScope().taskId().equals(text(issued.taskId()))||!request.executionScope().executionId().equals(executionId)
                        ||!request.authorizationRef().equals(text(issued.parentAuthorizationRef()))
                        ||!request.assets().memoryPolicyVersion().equals(text(plan.policyVersionId()))
                        ||!request.assets().modelRef().equals(operation.modelVersion())||!request.assets().promptRef().equals(operation.promptVersion())
                        ||!request.assets().schemaRef().equals(operation.outputSchemaVersion())||!"derive/1".equals(operation.policyVersion()))return false;
                if("customer-service".equals(scope.domain())) {
                    if(customers==null)return false;var run=customers.findRunForUpdate(executionId,scope.tenantId());
                    if(run==null||!scope.tenantId().equals(run.tenantId())||!scope.sessionId().equals(run.conversationId())||!runtimeId.equals(run.agentRunId()))return false;
                }else {
                    if(operations==null)return false;var run=operations.selectForUpdate(executionId,scope.tenantId());
                    if(run==null||!scope.tenantId().equals(run.getTenantId())||!scope.sessionId().equals(run.getConversationId())||!runtimeId.equals(run.getAgentRunId()))return false;
                }
                if(JSON.readValue(issued.policyJson(),MemoryAuthorization.Policy.class).maxPaidOperations()!=1)return false;
                var grants=JSON.readValue(issued.grantsJson(),new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
                if(grants.stream().noneMatch(g->g.nodeId().equals(operation.scope().subtaskId())&&g.executionAgentId().equals(operation.scope().executionAgentId())&&g.purpose().equals(operation.scope().purpose())))return false;
                var closure=MemoryPacketDigest.dependencies(frozen.sources().stream().flatMap(s->s.sourceDependencies().stream()).toList());
                return closure.equals(MemoryPacketDigest.dependencies(operation.safetyDependencies()))
                    &&closure.equals(MemoryPacketDigest.dependencies(operation.selectedSources()));
            }catch(java.io.IOException|IllegalArgumentException rejected){return false;}
            catch(MemoryException rejected){if(definiteRejection(rejected.code()))return false;throw rejected;}
        }));
    }
    private void requirePlan(PlanPO plan,IdentityFacade.Subject actor,MemoryScopeDTO scope,String executionId,MemoryDeriveRequest request) {
        if(plan==null||!"FROZEN".equals(plan.state())||!Arrays.equals(plan.executionId(),b(executionId))
                ||!Arrays.equals(plan.originalSessionRef(),b(actor.sessionRef()))||!Arrays.equals(plan.taskId(),b(request.executionScope().taskId()))
                ||!text(plan.policyVersionId()).equals(request.assets().memoryPolicyVersion()))throw failure("DERIVE_BINDING_CONFLICT");
        sources.checkOriginal(scope,plan.originalSessionRef(),plan.originalDeadline());
        if(request.deadlineEpochSeconds()>plan.originalDeadline()||request.deadlineEpochSeconds()<=sources.now())throw failure("DERIVE_DEADLINE_EXCEEDED");
    }
    private void verifyFrozen(MemoryDeriveRequest request,MemoryScopeDTO scope,String executionId,String planId,FrozenPlan plan) {
        var frozen=plan.frozen();
        if(!request.mode().equals(frozen.mode().name())||!request.planId().equals(planId)||!request.operationId().equals(planId)||!request.authorityRef().equals(planId)
                ||!request.executionScope().conversation().equals(neutral(scope))||!request.executionScope().executionId().equals(executionId)
                ||!request.executionScope().taskId().equals(plan.taskId())||request.sessionRevision()!=frozen.sessionRevision()
                ||request.sourceRevision()!=frozen.sourceRevision()||request.deadlineEpochSeconds()>plan.originalDeadline()
                ||(frozen.mode()!=DeriveMode.PROPOSALS&&frozen.requiredEntries().isEmpty())||request.sources().size()!=frozen.sources().size()
                ||!MemoryPacketDigest.canonicalDigest(request.events()).equals(MemoryPacketDigest.canonicalDigest(WIRE.valueToTree(frozen.events())))
                ||!MemoryPacketDigest.canonicalDigest(request.requiredEntries()).equals(MemoryPacketDigest.canonicalDigest(WIRE.valueToTree(frozen.requiredEntries()))))throw failure("DERIVE_BINDING_CONFLICT");
        for(int index=0;index<frozen.sources().size();index++) {
            var supplied=request.sources().get(index);var source=frozen.sources().get(index);String body=plan.bodies().get(index);
            if(!MemoryPacketDigest.canonicalDigest(supplied.metadata()).equals(MemoryPacketDigest.canonicalDigest(WIRE.valueToTree(source)))||!supplied.body().equals(body)||!supplied.bodySha256().equals(MemoryDeriveRequest.sha256(body)))throw failure("DERIVE_SOURCE_BODY_MISMATCH");
        }
    }
    private void requireRuntime(MemoryScopeDTO scope,String execution,MemoryDeriveRequest request) {
        String runtime,status;
        if(scope.domain().equals("operations")) {
            if(operations==null)throw failure("DERIVE_ORIGINAL_FRAME_REQUIRED");
            var row=operations.selectForUpdate(execution,scope.tenantId());
            if(row==null||!row.getTenantId().equals(scope.tenantId())||!row.getConversationId().equals(scope.sessionId()))throw failure("DERIVE_SCOPE_MISMATCH");
            runtime=row.getAgentRunId();status=row.getStatus();
        }else if(scope.domain().equals("customer-service")) {
            if(customers==null)throw failure("DERIVE_ORIGINAL_FRAME_REQUIRED");
            var row=customers.findRunForUpdate(execution,scope.tenantId());
            if(row==null||!row.tenantId().equals(scope.tenantId())||!row.conversationId().equals(scope.sessionId()))throw failure("DERIVE_SCOPE_MISMATCH");
            runtime=row.agentRunId();status=row.status();
        }else throw failure("DERIVE_SCOPE_MISMATCH");
        if(runtime==null||!runtime.equals(request.runtimeId())||status==null||Set.of("succeeded","failed","cancelled","timed_out","expired").contains(status.toLowerCase(Locale.ROOT)))throw failure("DERIVE_ORIGINAL_FRAME_REQUIRED");
        var packet=sources.packets.findPacket(b(scope.tenantId()),b(execution));
        if(packet==null||!text(packet.parentAuthorizationRef()).equals(request.authorizationRef()))throw failure("DERIVE_ORIGINAL_EXECUTION_REQUIRED");
        try {
            var policy=JSON.readValue(packet.policyJson(),MemoryAuthorization.Policy.class);
            if(policy.maxPaidOperations()!=1)throw failure("DERIVE_ORIGINAL_EXECUTION_REQUIRED");
        }catch(java.io.IOException invalid){throw failure("DERIVE_ORIGINAL_EXECUTION_REQUIRED");}
        var grants=read(packet.grantsJson(),new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
        if(grants.stream().noneMatch(g->g.nodeId().equals(request.executionScope().subtaskId())&&g.executionAgentId().equals(request.executionScope().executionAgentId())&&g.purpose().equals(request.executionScope().purpose())))throw failure("DERIVE_ORIGINAL_EXECUTION_REQUIRED");
    }
    private static SummarySegment verifyResponse(MemoryDeriveRequest request,MemoryDeriveResponse response,FrozenPlan frozen) {
        if(response==null)throw failure("MEMORY_DERIVE_RESPONSE_REQUIRED");
        try {response.validateBinding(request);}
        catch(IllegalArgumentException invalid){throw failure("DERIVE_BINDING_CONFLICT");}
        var benefit=response.benefit();var validation=response.validation();
        if(!"BENEFICIAL".equals(benefit.path("status").asText())||!"SUMMARY_BENEFIT_VERIFIED".equals(benefit.path("reason").asText()))throw failure("SUMMARY_NOT_BENEFICIAL");
        if(!"NOT_COMMITTED".equals(benefit.path("commit_status").asText())||!"NOT_COMMITTED".equals(validation.path("commit_status").asText())
                ||!"UNVERIFIED".equals(validation.path("free_text_quality").asText())||!benefit.path("T_before").isIntegralNumber()||!benefit.path("T_after").isIntegralNumber()
                ||benefit.path("T_after").asLong()<0||benefit.path("T_before").asLong()<=benefit.path("T_after").asLong())throw failure("MEMORY_DERIVE_RESPONSE_INVALID");
        SummarySegment candidate;
        try {candidate=WIRE.treeToValue(response.candidate().path("summary"),SummarySegment.class);}
        catch(com.fasterxml.jackson.core.JsonProcessingException invalid){throw failure("MEMORY_DERIVE_RESPONSE_INVALID");}
        var all=MemoryPacketDigest.dependencies(frozen.frozen().sources().stream().flatMap(s->s.sourceDependencies().stream()).toList());
        if(!MemoryPacketDigest.canonicalDigest(validation.path("source_dependencies")).equals(MemoryPacketDigest.canonicalDigest(WIRE.valueToTree(candidate.sourceDependencies())))||!MemoryPacketDigest.dependencies(candidate.sourceDependencies()).equals(all)
                ||!MemoryPacketDigest.canonicalDigest(validation.path("source_watermark")).equals(MemoryPacketDigest.canonicalDigest(WIRE.valueToTree(candidate.watermark())))
                ||validation.path("expires_at").asLong()!=candidate.expiresAt()||candidate.expiresAt()>frozen.frozen().expiresAt())throw failure("SUMMARY_STALE");
        if(!criticalDigest(request,candidate).equals(validation.path("frozen_critical_digest").asText()))throw failure("SUMMARY_REQUIRED_STATE_CHANGED");
        try {new MemorySummaryPolicy().validateSegment(candidate,frozen.frozen().sources(),frozen.frozen().events(),java.time.Instant.now().getEpochSecond(),frozen.frozen().sourceRevision());}
        catch(IllegalArgumentException invalid){throw failure("MEMORY_DERIVE_RESPONSE_INVALID");}
        return candidate;
    }
    private static List<com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate> verifyProposals(MemoryDeriveRequest request,MemoryDeriveResponse response,FrozenPlan frozen){
        if(response==null)throw failure("MEMORY_DERIVE_RESPONSE_REQUIRED");
        try{response.validateBinding(request);}catch(IllegalArgumentException invalid){throw failure("DERIVE_BINDING_CONFLICT");}
        var closure=MemoryPacketDigest.dependencies(frozen.frozen().sources().stream().flatMap(source->source.sourceDependencies().stream()).toList());
        var raw=new ArrayList<com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate>();
        for(var candidate:response.candidate().path("proposals"))raw.add(new com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate(candidate.path("kind").asText(),candidate.path("field_key").asText(),candidate.path("value").asText()));
        var validated=new ArrayList<com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate>();
        for(var candidate:response.validation().path("proposals_validated")){
            var declared=read(candidate.path("source_dependencies").toString(),new TypeReference<List<com.aiep.platformai.api.dto.MemoryContextPacket.Dependency>>(){});
            if(!"PROPOSED".equals(candidate.path("decision_status").asText())||!"NOT_REQUESTED".equals(candidate.path("index_status").asText())||!MemoryPacketDigest.dependencies(declared).equals(closure))throw failure("MEMORY_PROPOSAL_SOURCE_REQUIRED");
            validated.add(new com.aiep.aihub.api.memory.MemoryProposalContracts.Candidate(candidate.path("kind").asText(),candidate.path("field_key").asText(),candidate.path("value").asText()));
        }
        if(!new HashSet<>(raw).equals(new HashSet<>(validated))||validated.size()>16)throw failure("MEMORY_DERIVE_RESPONSE_INVALID");
        return List.copyOf(validated);
    }
    private static String criticalDigest(MemoryDeriveRequest request,SummarySegment candidate) {
        var critical=WIRE.createObjectNode();critical.set("scope",WIRE.valueToTree(request.executionScope().conversation()));
        critical.put("session_revision",request.sessionRevision());critical.put("source_revision",request.sourceRevision());
        critical.set("watermark",WIRE.valueToTree(candidate.watermark()));critical.put("mode",request.mode());critical.put("memory_policy_version",request.assets().memoryPolicyVersion());
        var sourceNodes=critical.putArray("sources");
        for(var source:request.sources()) {
            var metadata=(com.fasterxml.jackson.databind.node.ObjectNode)source.metadata();
            var purposes=new ArrayList<String>();metadata.path("allowed_purposes").forEach(p->purposes.add(p.asText()));
            var allowed=metadata.putArray("allowed_purposes");purposes.stream().distinct().sorted().forEach(allowed::add);sourceNodes.add(metadata);
        }
        critical.set("events",request.events());var entries=critical.putArray("required_entries");
        for(var entry:request.requiredEntries()){var structure=(com.fasterxml.jackson.databind.node.ObjectNode)entry.deepCopy();structure.remove("text");entries.add(structure);}
        return MemoryPacketDigest.canonicalDigest(critical);
    }
    private static void outsideTransaction(){if(TransactionSynchronizationManager.isActualTransactionActive())throw failure("DERIVE_OUTSIDE_TRANSACTION_REQUIRED");}
}
