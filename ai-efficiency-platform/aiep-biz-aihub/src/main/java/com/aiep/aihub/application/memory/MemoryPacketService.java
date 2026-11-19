package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
import com.aiep.aihub.repository.memory.MemoryRefreshMapper;
import com.aiep.platformai.api.dto.MemoryContextWait;
import com.aiep.platformai.api.dto.MemoryResumeRequest;
import com.aiep.platformai.api.dto.MemoryResumeReceipt;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryAuthorization;
import com.aiep.platformai.api.dto.MemoryContextEnvelope;
import com.aiep.platformai.api.dto.MemoryContextPacket;
import com.aiep.platformai.api.dto.MemoryPacketDigest;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 只签发已发布策略下的本人确定性偏好；持久表只存不可变引用，不保存偏好值明文。 */
@Service
public class MemoryPacketService {
    @Autowired(required=false)
    private MemorySummaryService summaryService;
    @Autowired(required=false)
    private MemorySharingService sharingService;
    @Autowired(required=false)
    private MemoryKnowledgeService knowledgeService;
    @Autowired(required=false)
    private MemoryDerivePlanService derivePlans;
    private static final ObjectMapper JSON = new ObjectMapper();
    private final boolean enabled;
    private final MemoryMapper memory;
    private final MemoryPacketMapper packets;
    private final MemoryScopePolicy scopes;
    private final MemorySessionBindingService bindings;
    private final MemoryPolicyService policies;
    private final MemoryPreferenceService preferences;
    private final MemoryDependencyService dependencies;
    private final MemoryValueCodec codec;
    private final TransactionTemplate transactions;
    private final Clock clock;
    private final boolean refreshEnabled;
    private final MemoryRefreshMapper refresh;
    private final IdentityFacade identity;

    @Autowired public MemoryPacketService(@Value("${aiep.memory.packet-enabled:false}") boolean enabled,
            MemoryMapper memory, MemoryPacketMapper packets, MemoryScopePolicy scopes,
            MemorySessionBindingService bindings, MemoryPolicyService policies, MemoryPreferenceService preferences,
            MemoryDependencyService dependencies, MemoryValueCodec codec, PlatformTransactionManager manager,
            @Value("${aiep.memory.refresh-enabled:false}") boolean refreshEnabled,
            org.springframework.beans.factory.ObjectProvider<MemoryRefreshMapper> refresh, IdentityFacade identity) {
        this(enabled,memory,packets,scopes,bindings,policies,preferences,dependencies,codec,manager,Clock.systemUTC(),refreshEnabled,refresh.getIfAvailable(),identity);
    }
    public MemoryPacketService(boolean enabled, MemoryMapper memory, MemoryPacketMapper packets, MemoryScopePolicy scopes,
            MemorySessionBindingService bindings, MemoryPolicyService policies, MemoryPreferenceService preferences,
            MemoryDependencyService dependencies, MemoryValueCodec codec, PlatformTransactionManager manager, Clock clock) {
        this(enabled,memory,packets,scopes,bindings,policies,preferences,dependencies,codec,manager,clock,false,null,null);
    }
    public MemoryPacketService(boolean enabled, MemoryMapper memory, MemoryPacketMapper packets, MemoryScopePolicy scopes,
            MemorySessionBindingService bindings, MemoryPolicyService policies, MemoryPreferenceService preferences,
            MemoryDependencyService dependencies, MemoryValueCodec codec, PlatformTransactionManager manager, Clock clock,
            boolean refreshEnabled, MemoryRefreshMapper refresh, IdentityFacade identity) {
        this.enabled=enabled; this.memory=memory; this.packets=packets; this.scopes=scopes; this.bindings=bindings;
        this.policies=policies; this.preferences=preferences; this.dependencies=dependencies; this.codec=codec;
        this.transactions=new TransactionTemplate(manager); this.clock=clock;
        this.refreshEnabled=refreshEnabled; this.refresh=refresh; this.identity=identity;
    }
    public boolean enabled() { return enabled; }
    /** 当前事件只按首次真正签发的包核manifest；分域禁用不虚构记忆执行。 */
    public boolean hasIssuedExecution(String tenantId,String executionId){return packets.findPacket(bytes(tenantId),bytes(executionId))!=null;}
    public boolean refreshEnabled() { return enabled&&refreshEnabled; }

    public MemoryScopeDTO issuedScope(String tenantId,String executionId) {
        var issued=packets.findPacket(bytes(tenantId),bytes(executionId));
        if(issued==null)throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
        try {return JSON.readValue(issued.scopeJson(),MemoryScopeDTO.class);}
        catch(java.io.IOException error){throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");}
    }

    public List<MemoryContextPacket.Dependency> verifyManifest(MemoryScopeDTO scope, String executionId,
            String runtimeId, com.aiep.platformai.api.dto.MemoryRuntimeManifest manifest) {
        var issued = packets.findPacket(bytes(scope.tenantId()),bytes(executionId));
        if(issued==null || !Arrays.equals(issued.userId(),bytes(scope.userId())) || manifest==null
                || !executionId.equals(manifest.executionId()) || !runtimeId.equals(manifest.runtimeId())
                || !text(issued.packetId()).equals(manifest.packetId())
                || manifest.manifests().isEmpty()) throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
        var authorizedRevisions=new java.util.HashSet<Long>();authorizedRevisions.add(issued.packetRevision());
        MemoryRefreshMapper.Candidate technicalCurrent=null;
        if(refreshEnabled) {
            requireRefresh();authorizedRevisions.addAll(refresh.authorizedRevisions(bytes(scope.tenantId()),bytes(executionId)));
            technicalCurrent=refresh.findCurrent(bytes(scope.tenantId()),bytes(executionId));
        }
        if(!authorizedRevisions.contains(manifest.packetRevision())&&(technicalCurrent==null||technicalCurrent.targetRevision()!=manifest.packetRevision()))
            throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
        try {
            var originalScope=JSON.readValue(issued.scopeJson(),MemoryContextEnvelope.Scope.class);
            var allowed=JSON.readValue(issued.dependenciesJson(),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            var inputDependencies=JSON.convertValue(JSON.readTree(issued.referencesJson()).path("input_dependencies"),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            if(inputDependencies==null||inputDependencies.isEmpty()||!allowed.containsAll(inputDependencies))throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
            var grants=JSON.readValue(issued.grantsJson(),new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
            if(!JSON.valueToTree(scope).equals(JSON.valueToTree(originalScope)))throw new MemoryException("MEMORY_SCOPE_DENIED");
            var actual=new ArrayList<MemoryContextPacket.Dependency>();
            for(var operation:manifest.manifests()) {
                var opScope=operation.scope();
                boolean derive="memory.derive".equals(operation.nodeId());
                boolean deriveBound=derive&&derivePlans!=null&&derivePlans.verifyManifest(scope,executionId,runtimeId,issued,operation);
                if(!opScope.conversation().equals(originalScope)||!opScope.taskId().equals(text(issued.taskId()))
                    ||!opScope.executionId().equals(executionId)||!operation.packetId().equals(manifest.packetId())
                    ||!authorizedRevisions.contains(operation.packetRevision())
                    ||(derive?!deriveBound:grants.stream().noneMatch(grant->grant.nodeId().equals(operation.nodeId())&&grant.executionAgentId().equals(opScope.executionAgentId())&&grant.purpose().equals(opScope.purpose())))
                    ||!allowed.containsAll(operation.safetyDependencies())
                    ||(derive?!deriveBound:!validInputClosure(scope,issued,operation,inputDependencies))
                    ||!MemoryPacketDigest.dependencies(operation.safetyDependencies()).equals(MemoryPacketDigest.dependencies(operation.selectedSources())))
                    throw new MemoryException("MEMORY_MANIFEST_SOURCE_DENIED");
                actual.addAll(operation.safetyDependencies());
            }
            var closure=MemoryPacketDigest.dependencies(actual);
            dependencies.requireCurrent(scope,closure);return closure;
        }catch(java.io.IOException failure){throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");}
    }

    public MemoryContextEnvelope issueMessage(MemoryScopeDTO scope, String javaRunId, String messageId,
            JsonNode actualRequest, List<MemoryContextPacket.Dependency> historyDependencies) {
        return issueMessage(scope,javaRunId,messageId,actualRequest,historyDependencies,null);
    }
    /** CSR原wire无消息ID，可信历史投影经独立内部参数绑定，不改员工请求或原requestDigest。 */
    public MemoryContextEnvelope issueMessage(MemoryScopeDTO scope,String javaRunId,String messageId,
            JsonNode actualRequest,List<MemoryContextPacket.Dependency> historyDependencies,List<com.aiep.platformai.api.dto.MemoryHistoryMessage> originalHistory) {
        if (!enabled) return new ConversationScopeResolver().envelope(scope);
        var actor = scopes.currentActor();
        scopes.require(actor, scope, Set.of()); bindings.require(actor, scope);
        if (scope.sessionId() == null) throw new MemoryException("MEMORY_MESSAGE_SCOPE_REQUIRED");
        try {
            var published = memory.findPublishedPolicy(bytes(scope.tenantId()), scope.domain());
            if (published == null) throw new MemoryException("FEATURE_DISABLED");
            MemoryPolicyService.requireArtifactPolicy(published);
            var context = JSON.readTree(published.policyJson()).path("context");
            long timeout = context.path("executionTimeoutSeconds").asLong(0);
            long retention = context.path("sourceRetentionSeconds").asLong(0);
            if (timeout <= 0 || retention <= 0 || timeout > 600 || retention > 31536000)
                throw new MemoryException("MEMORY_POLICY_INVALID");
            String digest = packets.findUserMessageHash(bytes(scope.tenantId()), bytes(scope.userId()), scope.domain(), bytes(scope.sessionId()), bytes(messageId));
            String supplied = java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                    .digest(actualRequest.path("message").asText().getBytes(StandardCharsets.UTF_8)));
            if (digest == null || !digest.equals(supplied)) throw new MemoryException("MEMORY_SOURCE_CHANGED");
            String sourceId = UUID.nameUUIDFromBytes((scope.tenantId()+"\u0000"+messageId+"\u0000"+digest).getBytes(StandardCharsets.UTF_8)).toString();
            return transactions.execute(status -> {
                var source = packets.findSource(bytes(scope.tenantId()), bytes(sourceId));
                if (source == null) {
                    if (packets.insertInputSource(bytes(scope.tenantId()), bytes(sourceId), bytes(messageId), bytes(digest), clock.instant().plusSeconds(retention)) != 1)
                        throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
                    source = packets.findSource(bytes(scope.tenantId()), bytes(sourceId));
                }
                var direct = new MemoryContextPacket.Dependency("CURRENT_USER_MESSAGE", sourceId, digest, source.grantEpoch(), source.sourceEpoch(), source.deletionEpoch());
                dependencies.record(scope, "MESSAGE", messageId, digest, javaRunId, List.of(direct), List.of(List.of(direct)), List.of());
                var all = new ArrayList<>(historyDependencies); all.add(direct);
                return issueWithHistory(actor, scope, javaRunId, javaRunId, actualRequest, clock.instant().getEpochSecond()+timeout, all,originalHistory);
            });
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | java.security.NoSuchAlgorithmException failure) { throw new MemoryException("MEMORY_POLICY_INVALID"); }
    }

    public MemoryContextEnvelope issue(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId, String executionId,
            JsonNode actualRequest, long originalDeadline, List<MemoryContextPacket.Dependency> actualInputDependencies) {
        return issueWithHistory(actor,scope,taskId,executionId,actualRequest,originalDeadline,actualInputDependencies,null);
    }
    private MemoryContextEnvelope issueWithHistory(IdentityFacade.Subject actor,MemoryScopeDTO scope,String taskId,String executionId,
            JsonNode actualRequest,long originalDeadline,List<MemoryContextPacket.Dependency> actualInputDependencies,List<com.aiep.platformai.api.dto.MemoryHistoryMessage> originalHistory) {
        if (!enabled) return new ConversationScopeResolver().envelope(scope);
        scopes.require(actor, scope, Set.of()); bindings.require(actor, scope); codec.currentVersion();
        MemoryMapper.identity(taskId); MemoryMapper.identity(executionId);
        if (actualRequest == null || !actualRequest.isObject() || actualInputDependencies.isEmpty())
            throw new MemoryException("MEMORY_CURRENT_INPUT_DEPENDENCIES_REQUIRED");
        ObjectNode request = actualRequest.deepCopy(); request.remove("memory_context");
        String requestDigest = MemoryPacketDigest.canonicalDigest(request);
        try {
            return transactions.execute(status -> issueTransaction(actor, scope, taskId, executionId, requestDigest, originalDeadline, actualInputDependencies,request,originalHistory));
        } catch (DuplicateKeyException conflict) {
            return transactions.execute(status -> {
                var original = packets.findPacket(bytes(scope.tenantId()), bytes(executionId));
                if (original == null) throw new MemoryException("MEMORY_EXECUTION_CONFLICT");
                return restore(actor, scope, taskId, requestDigest, original);
            });
        } catch(org.springframework.dao.DataAccessException failure) {
            if(refreshEnabled)throw new MemoryException("MEMORY_REFRESH_SCHEMA_REQUIRED");
            throw failure;
        }
    }

    private MemoryContextEnvelope issueTransaction(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId,
            String executionId, String requestDigest, long deadline, List<MemoryContextPacket.Dependency> actualInputs,JsonNode request,List<com.aiep.platformai.api.dto.MemoryHistoryMessage> originalHistory) {
        var original = packets.findPacket(bytes(scope.tenantId()), bytes(executionId));
        if (original != null) return restore(actor, scope, taskId, requestDigest, original);
        long now = clock.instant().getEpochSecond();
        if (deadline <= now || deadline > now + 600) throw new MemoryException("MEMORY_EXECUTION_EXPIRED");
        var published = memory.findPublishedPolicy(bytes(scope.tenantId()), scope.domain());
        if (published == null || !"memory-policy/1".equals(published.schemaVersion())) throw new MemoryException("FEATURE_DISABLED");
        MemoryPolicyService.requireArtifactPolicy(published);
        try {
            JsonNode context = JSON.readTree(published.policyJson()).path("context");
            if (!context.path("enabled").asBoolean(false)) throw new MemoryException("FEATURE_DISABLED");
            long ttl = context.path("packetTtlSeconds").asLong(0);
            if (ttl <= 0 || ttl > 60) throw new MemoryException("MEMORY_POLICY_INVALID");
            var grants = JSON.convertValue(context.path("executionGrants"), new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
            if (grants == null || grants.isEmpty()) throw new MemoryException("MEMORY_POLICY_INVALID");
            var agents = new TreeSet<String>(); agents.add(scope.topLevelAgentId()); grants.forEach(grant -> agents.add(grant.executionAgentId()));
            var fields = new TreeSet<String>();
            for (String field : List.of("response.language", "response.detail_level", "response.format")) {
                try { policies.require(scope, field, null); fields.add(field); }
                catch (MemoryException rejected) { if (!"FEATURE_DISABLED".equals(rejected.code())) throw rejected; }
            }
            if (fields.isEmpty()) throw new MemoryException("FEATURE_DISABLED");
            var selected = preferences.list(actor, scope, fields);
            policies.requireVersionArtifacts(bytes(scope.tenantId()),selected.stream()
                .map(preference->new MemoryMapper.VersionIdentityPO(bytes(preference.id()),bytes(preference.versionId()))).toList());
            var items = new ArrayList<MemoryContextPacket.Item>();
            var all = new ArrayList<>(actualInputs);
            long expiry = Math.min(deadline, now + ttl);
            MemoryKnowledgeService.Projection knowledgeContext=knowledgeService==null?null:knowledgeService.issue(actor,scope,executionId,request,deadline,context);
            if(knowledgeContext!=null&&!refreshEnabled)throw new MemoryException("MEMORY_KNOWLEDGE_ORIGINAL_AUTHORITY_REQUIRED");
            if(knowledgeContext!=null){all.addAll(knowledgeContext.dependencies());expiry=Math.min(expiry,knowledgeContext.expiresAt());}
            MemorySummaryService.ContextProjection summaryContext=null;
            List<com.aiep.platformai.api.dto.MemoryHistoryMessage> summaryHistory=null;
            if(summaryService!=null&&summaryService.enabled()&&request.path("history").isArray()) {
                if("customer-service".equals(scope.domain())) {
                    if(originalHistory!=null&&originalHistory.size()==request.path("history").size()) {
                        for(int i=0;i<originalHistory.size();i++)if(!originalHistory.get(i).role().equals(request.path("history").get(i).path("role").asText())||!originalHistory.get(i).content().equals(request.path("history").get(i).path("content").asText()))throw new MemoryException("MEMORY_SOURCE_CHANGED");
                        summaryHistory=List.copyOf(originalHistory);
                    }
                }else summaryHistory=JSON.convertValue(request.path("history"),new TypeReference<List<com.aiep.platformai.api.dto.MemoryHistoryMessage>>(){});
                summaryContext=summaryHistory==null?null:summaryService.contextProjection(actor,scope,summaryHistory);
                if(summaryContext!=null) { all.addAll(summaryContext.dependencies());expiry=Math.min(expiry,summaryContext.expiresAt()); }
            }
            for (var preference : selected) {
                var closure = dependencies.dependencies(scope, "MEMORY_VERSION", preference.id(), preference.versionId());
                if (closure.isEmpty()) throw new MemoryException("MEMORY_SOURCE_CHANGED");
                items.add(new MemoryContextPacket.Item(preference.id(), preference.versionId(), preference.fieldKey(), preference.value(), closure));
                all.addAll(closure); expiry = Math.min(expiry, preference.expiresAt().getEpochSecond());
            }
            if(sharingService!=null&&sharingService.enabled()) {
                for(var projected:sharingService.select(actor,scope,fields)) {
                    // 本域私有明确值优先；不同共享scope的矛盾值已在共享服务中整体剔除。
                    if(items.stream().anyMatch(item->item.fieldKey().equals(projected.item().fieldKey())))continue;
                    items.add(projected.item());all.addAll(projected.item().safetyDependencies());
                    expiry=Math.min(expiry,projected.expiresAt().getEpochSecond());
                }
            }
            var closure = MemoryPacketDigest.dependencies(all);
            validateSharingDependencies(actor,scope,closure);
            var sourceTypes = JSON.convertValue(context.path("sourceTypes"), new TypeReference<List<String>>(){});
            if (sourceTypes == null || sourceTypes.isEmpty() || closure.stream().anyMatch(dep -> !sourceTypes.contains(dep.sourceType())))
                throw new MemoryException("MEMORY_SOURCE_TYPE_DENIED");
            long sourceRetention = dependencies.requireCurrent(scope, closure).getEpochSecond();
            expiry = Math.min(expiry, sourceRetention);
            if (expiry <= now) throw new MemoryException("MEMORY_SOURCE_CHANGED");
            var policy = new MemoryAuthorization.Policy(text(published.id()), text(published.versionId()), scope.domain(),
                    List.copyOf(agents), true, List.of("semantic"), List.of(), List.of("USER_PRIVATE"), List.copyOf(fields),
                    List.of("LOW"), true, false, true, sourceTypes,
                    0, 0, 0, 0, "disabled", "block", "1", "none", "none");
            var neutralScope = new MemoryContextEnvelope.Scope(scope.tenantId(), scope.userId(), scope.domain(), scope.topLevelAgentId(), scope.sessionKind(), scope.sessionId());
            int maxPaidOperations=summaryContext!=null&&refreshEnabled&&context.path("summary").path("maxPaidOperations").isIntegralNumber()&&context.path("summary").path("maxPaidOperations").canConvertToInt()
                &&context.path("summary").path("maxPaidOperations").intValue()==1?1:0;
            var semanticPolicy=JSON.readTree(published.policyJson()).path("semantic");
            if(refreshEnabled&&semanticPolicy.path("enabled").isBoolean()&&semanticPolicy.path("enabled").booleanValue()
                    &&semanticPolicy.path("maxPaidOperations").isIntegralNumber()&&semanticPolicy.path("maxPaidOperations").canConvertToInt()&&semanticPolicy.path("maxPaidOperations").intValue()==1) {
                MemoryPolicyService.requireProvisionedIndex(JSON.readTree(published.policyJson()));maxPaidOperations=1;
            }
            var proposalMode=context.path("summary").path("mode");var proposalPolicy=JSON.readTree(published.policyJson()).path("proposals");
            boolean proposalDerive=maxPaidOperations==1&&proposalMode.isTextual()&&Set.of("PROPOSALS","BOTH").contains(proposalMode.textValue())
                &&proposalPolicy.path("enabled").isBoolean()&&proposalPolicy.path("enabled").booleanValue();
            policy=new MemoryAuthorization.Policy(policy.policyId(),policy.version(),policy.domain(),policy.agentIds(),policy.enabled(),policy.readableLayers(),proposalDerive?List.of("PREFERENCE"):policy.writableKinds(),policy.allowedScopes(),policy.fieldAllowlist(),
                policy.sensitivityLevels(),policy.confirmationRequired(),proposalDerive,policy.sharedApprovalRequired(),policy.sourceTypes(),policy.retentionDays(),policy.recallTopK(),policy.recallTokenLimit(),maxPaidOperations,
                policy.degradationMode(),policy.sourceDeletionMode(),policy.schemaVersion(),policy.modelVersion(),policy.tokenizerVersion());
            var packet = new MemoryContextPacket(UUID.randomUUID().toString(), 1, neutralScope, taskId, executionId,
                    policy.version(), 1, now, expiry, 0, 0, 0, requestDigest, executionId, items, closure);
            var refs = JSON.valueToTree(items);
            refs.forEach(item -> ((ObjectNode) item).remove("value"));
            var referenceSnapshot=JSON.createObjectNode();referenceSnapshot.put("schema_version","memory-packet-references/2");referenceSnapshot.set("items",refs);
            referenceSnapshot.set("input_dependencies",JSON.valueToTree(MemoryPacketDigest.dependencies(actualInputs)));
            if(summaryContext!=null)referenceSnapshot.put("summary_context_refs",summaryContext.referenceJson());
            String derivePlanId=maxPaidOperations==1&&summaryContext!=null?"derive-"+MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of(scope.tenantId(),taskId))):null;
            if(knowledgeContext!=null)referenceSnapshot.put("knowledge_context_json",knowledgeContext.json());
            if(derivePlanId!=null)referenceSnapshot.put("derive_plan_id",derivePlanId);
            var row = new MemoryPacketMapper.PacketRow(bytes(scope.tenantId()), bytes(executionId), bytes(packet.packetId()), 1,
                    bytes(scope.userId()), bytes(taskId), JSON.writeValueAsString(neutralScope), JSON.writeValueAsString(policy),
                    JSON.writeValueAsString(grants), JSON.writeValueAsString(referenceSnapshot), JSON.writeValueAsString(closure), requestDigest,
                    MemoryPacketDigest.digest(packet), MemoryPacketDigest.semanticDigest(packet), requestDigest, bytes(executionId),
                    1, 0, 0, 0, deadline, now, expiry);
            if (packets.insertPacket(row) != 1) throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
            if (refreshEnabled) {
                requireRefresh();
                if(actor.sessionRef()==null||actor.sessionRef().isBlank())throw new MemoryException("MEMORY_IDENTITY_REQUIRED");
                if(refresh.insertAnchor(new MemoryRefreshMapper.Anchor(row.tenantId(),row.executionId(),row.userId(),row.packetId(),
                    row.packetRevision(),row.executionRevision(),row.requestDigest(),row.semanticDigest(),row.originalDeadline(),
                    bytes(actor.sessionRef()),Math.toIntExact(ttl),sourceRetention))!=1)throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
            }
            dependencies.record(scope, "EXECUTION", executionId, "1", executionId, closure, List.of(closure), List.of());
            if(knowledgeContext!=null)knowledgeService.recordAuthority(scope,executionId,knowledgeContext);
            String deriveTemplate=derivePlanId==null||summaryHistory==null?null:summaryService.bootstrapDeriveTemplate(actor,scope,executionId,derivePlanId,
                summaryHistory.stream().map(com.aiep.platformai.api.dto.MemoryHistoryMessage::messageId).toList());
            return new MemoryContextEnvelope("memory-context/1", "EXACT_ONLY", neutralScope, packet,
                    new MemoryAuthorization(policy, grants, deadline, row.packetDigest(), row.semanticDigest(), requestDigest,MemoryPacketDigest.dependencies(actualInputs),summaryContext==null?null:summaryContext.json(),deriveTemplate,knowledgeContext==null?null:knowledgeContext.json()));
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | IllegalArgumentException failure) { throw new MemoryException("MEMORY_POLICY_INVALID"); }
    }

    private MemoryContextEnvelope restore(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId,
            String requestDigest, MemoryPacketMapper.PacketRow row) {
        if (!Arrays.equals(bytes(scope.userId()), row.userId()) || !Arrays.equals(bytes(taskId), row.taskId())
                || !requestDigest.equals(row.requestDigest())) throw new MemoryException("MEMORY_EXECUTION_CONFLICT");
        if (clock.instant().getEpochSecond() >= Math.min(row.expiresAt(), row.originalDeadline())) throw new MemoryException("MEMORY_EXECUTION_EXPIRED");
        return hydrate(actor,scope,row);
    }
    private MemoryContextEnvelope hydrate(IdentityFacade.Subject actor,MemoryScopeDTO scope,MemoryPacketMapper.PacketRow row) {
        try {
            var neutralScope = JSON.readValue(row.scopeJson(), MemoryContextEnvelope.Scope.class);
            if (!JSON.valueToTree(scope).equals(JSON.valueToTree(neutralScope))) throw new MemoryException("MEMORY_SCOPE_DENIED");
            var policy = JSON.readValue(row.policyJson(), MemoryAuthorization.Policy.class);
            MemoryPolicyService.requireArtifactPolicy(memory.findPolicyVersion(bytes(scope.tenantId()),bytes(policy.policyId()),bytes(policy.version())));
            var grants = JSON.readValue(row.grantsJson(), new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
            var closure = JSON.readValue(row.dependenciesJson(), new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            validateSharingDependencies(actor,scope,closure);
            dependencies.requireCurrent(scope, closure);
            var items = new ArrayList<MemoryContextPacket.Item>();
            var referenceSnapshot=JSON.readTree(row.referencesJson());
            String knowledgeContextJson=null;
            if(referenceSnapshot.has("knowledge_context_json")) {
                if(knowledgeService==null)throw new MemoryException("MEMORY_SOURCE_CHANGED");
                knowledgeContextJson=knowledgeService.hydrate(actor,scope,referenceSnapshot.path("knowledge_context_json").asText());
            }
            if(!"memory-packet-references/2".equals(referenceSnapshot.path("schema_version").asText())||!referenceSnapshot.path("items").isArray()||!referenceSnapshot.path("input_dependencies").isArray())throw new MemoryException("MEMORY_SOURCE_CHANGED");
            var inputDependencies=JSON.convertValue(referenceSnapshot.path("input_dependencies"),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            String summaryContextJson=null;
            if(referenceSnapshot.has("summary_context_refs")) {
                if(summaryService==null||!summaryService.enabled())throw new MemoryException("MEMORY_SOURCE_CHANGED");
                summaryContextJson=summaryService.rebuildProjection(actor,scope,referenceSnapshot.path("summary_context_refs").asText()).json();
            }
            String deriveTemplateJson=null;
            if(referenceSnapshot.has("derive_plan_id")) {
                if(summaryService==null||!summaryService.enabled())throw new MemoryException("MEMORY_SOURCE_CHANGED");
                deriveTemplateJson=summaryService.rebuildDeriveTemplate(actor,scope,text(row.executionId()),referenceSnapshot.path("derive_plan_id").asText());
            }
            var artifactVersions=new ArrayList<MemoryMapper.VersionIdentityPO>();
            for(var ref:referenceSnapshot.path("items"))if(!ref.path("item_id").asText().startsWith("share:"))artifactVersions.add(new MemoryMapper.VersionIdentityPO(bytes(ref.path("item_id").asText()),bytes(ref.path("version").asText())));
            policies.requireVersionArtifacts(bytes(scope.tenantId()),artifactVersions);
            for (var ref : referenceSnapshot.path("items")) {
                if(ref.path("item_id").asText().startsWith("share:")) {
                    if(sharingService==null||!sharingService.enabled())throw new MemoryException("MEMORY_SOURCE_CHANGED");
                    var live=sharingService.hydrate(actor,scope,ref.path("item_id").asText().substring(6)).item();
                    var deps=JSON.convertValue(ref.path("safety_dependencies"),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
                    if(!live.version().equals(ref.path("version").asText())||!live.fieldKey().equals(ref.path("field_key").asText())
                            ||!MemoryPacketDigest.dependencies(deps).equals(live.safetyDependencies()))throw new MemoryException("MEMORY_SOURCE_CHANGED");
                    items.add(live);continue;
                }
                var live = preferences.get(actor, scope, ref.path("item_id").asText()).preference();
                if (!live.versionId().equals(ref.path("version").asText()) || !live.fieldKey().equals(ref.path("field_key").asText()))
                    throw new MemoryException("MEMORY_SOURCE_CHANGED");
                var deps = JSON.convertValue(ref.path("safety_dependencies"), new TypeReference<List<MemoryContextPacket.Dependency>>(){});
                if(!MemoryPacketDigest.dependencies(deps).equals(dependencies.dependencies(scope,"MEMORY_VERSION",live.id(),live.versionId())))
                    throw new MemoryException("MEMORY_SOURCE_CHANGED");
                items.add(new MemoryContextPacket.Item(live.id(), live.versionId(), live.fieldKey(), live.value(), deps));
            }
            var packet = new MemoryContextPacket(text(row.packetId()), row.packetRevision(), neutralScope, text(row.taskId()),
                    text(row.executionId()), policy.version(), row.executionRevision(), row.issuedAt(), row.expiresAt(),
                    row.grantEpoch(), row.sourceEpoch(), row.deletionEpoch(), row.semanticInputHash(), text(row.parentAuthorizationRef()), items, closure);
            return new MemoryContextEnvelope("memory-context/1", "EXACT_ONLY", neutralScope, packet,
                    new MemoryAuthorization(policy, grants, row.originalDeadline(), row.packetDigest(), row.semanticDigest(), row.requestDigest(),inputDependencies,summaryContextJson,deriveTemplateJson,knowledgeContextJson));
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | IllegalArgumentException failure) { throw new MemoryException("MEMORY_SOURCE_CHANGED"); }
    }
    private void requireRefresh() {
        if(!enabled||!refreshEnabled)throw new MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
        if(refresh==null||identity==null)throw new MemoryException("MEMORY_REFRESH_SCHEMA_REQUIRED");
    }
    /** 发布/重放前沿原不可逆登录引用复查当前KB目录与ACL，不借SSE新连接身份。 */
    public void validateKnowledgePublication(MemoryScopeDTO scope,String executionId) {
        var issued=packets.findPacket(bytes(scope.tenantId()),bytes(executionId));if(issued==null)throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
        try {
            var refs=JSON.readTree(issued.referencesJson());if(!refs.has("knowledge_context_json"))return;
            requireRefresh();if(knowledgeService==null)throw new MemoryException("MEMORY_SOURCE_CHANGED");
            var actor=originalActor(refresh.findAnchor(bytes(scope.tenantId()),bytes(executionId)),scope);
            knowledgeService.hydrate(actor,scope,refs.path("knowledge_context_json").asText());
        }catch(java.io.IOException invalid){throw new MemoryException("MEMORY_KNOWLEDGE_DIRECTORY_INVALID");}
    }
    /** 后台只使用首次持久的不可逆登录引用，不读取当前请求线程身份。 */
    private IdentityFacade.Subject originalActor(MemoryRefreshMapper.Anchor anchor,MemoryScopeDTO scope) {
        if(anchor==null)throw new MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
        String session=text(anchor.originalSessionRef());
        if(!Arrays.equals(anchor.tenantId(),bytes(scope.tenantId()))||!Arrays.equals(anchor.userId(),bytes(scope.userId())))
            throw new MemoryException("MEMORY_SCOPE_DENIED");
        var actor=identity.refresh(scope.tenantId(),scope.userId(),session).orElseThrow(()->new MemoryException("ACCESS_REVOKED"));
        if(!scope.tenantId().equals(actor.tenantId())||!scope.userId().equals(actor.userId())||!session.equals(actor.sessionRef()))
            throw new MemoryException("ACCESS_REVOKED");
        scopes.require(actor,scope,Set.of());bindings.require(actor,scope);return actor;
    }
    /** 仅重建原refs；候选外壳和完整请求指纹先提交，再交给调用方发送。 */
    public MemoryResumeRequest prepareRefreshForWait(MemoryScopeDTO scope,MemoryContextWait wait) {
        requireRefresh();
        try {return transactions.execute(status->prepareRefreshTransaction(scope,wait,null));}
        catch(org.springframework.dao.DataAccessException failure){throw new MemoryException("MEMORY_REFRESH_SCHEMA_REQUIRED");}
    }
    public MemoryResumeRequest prepareRefresh(MemoryScopeDTO scope,MemoryContextWait wait,String requestId) {
        requireRefresh();bytes(requestId);
        try {return transactions.execute(status->prepareRefreshTransaction(scope,wait,requestId));}
        catch(org.springframework.dao.DataAccessException failure){throw new MemoryException("MEMORY_REFRESH_SCHEMA_REQUIRED");}
    }
    private MemoryResumeRequest prepareRefreshTransaction(MemoryScopeDTO scope,MemoryContextWait wait,String requestId) {
        var tenant=bytes(scope.tenantId());var execution=bytes(wait.executionId());
        refresh.lockPacket(tenant,execution);
        var anchor=refresh.findAnchor(tenant,execution);var actor=originalActor(anchor,scope);
        var row=packets.findPacket(tenant,execution);
        if(row==null||!Arrays.equals(row.packetId(),anchor.packetId())||!Arrays.equals(row.userId(),anchor.userId())
            ||row.packetRevision()!=anchor.initialPacketRevision()||row.executionRevision()!=anchor.executionRevision()
            ||!row.requestDigest().equals(anchor.requestDigest())||!row.semanticDigest().equals(anchor.semanticDigest())
            ||row.originalDeadline()!=anchor.originalDeadline())throw new MemoryException("MEMORY_AUTHORITY_UNAVAILABLE");
        var original=hydrate(actor,scope,row);
        var published=memory.findPublishedPolicy(tenant,scope.domain());
        if(published==null||!Arrays.equals(published.id(),bytes(original.authorization().policy().policyId()))
            ||!Arrays.equals(published.versionId(),bytes(original.authorization().policy().version())))throw new MemoryException("MEMORY_SOURCE_CHANGED");
        if(!MemoryPacketDigest.digest(original.packet()).equals(row.packetDigest())||!MemoryPacketDigest.semanticDigest(original.packet()).equals(row.semanticDigest()))
            throw new MemoryException("MEMORY_SOURCE_CHANGED");
        if(refresh.invalidCurrentInputs(tenant,bytes(scope.userId()),scope.domain(),scope.sessionId()==null?null:bytes(scope.sessionId()),execution)!=0)
            throw new MemoryException("MEMORY_SOURCE_CHANGED");
        if(!wait.scope().equals(original.scope())||!wait.taskId().equals(text(row.taskId()))||wait.originalDeadline()!=row.originalDeadline()
            ||wait.expectedExecutionRevision()!=row.executionRevision()||!wait.semanticInputHash().equals(row.semanticInputHash()))
            throw new MemoryException("MEMORY_RESUME_CONFLICT");
        if(requestId==null) {
            var latest=refresh.findLatestForWait(tenant,execution,bytes(wait.waitEventId()));
            // 只有已持久的B前未应用过期可换候选；时钟已过、HTTP未知和PENDING均重放原ID。
            if(latest!=null&&!"EXPIRED_UNAPPLIED".equals(latest.phase()))requestId=text(latest.resumeRequestId());
            else {
                long target=Math.max(row.packetRevision(),refresh.highestRevision(tenant,execution))+1;
                requestId=MemoryPacketDigest.canonicalDigest(JSON.valueToTree(List.of("memory-context-resume-key/2",scope.tenantId(),wait.executionId(),wait.waitEventId(),target)));
            }
        }
        var previous=refresh.findCandidate(tenant,execution,bytes(requestId));
        if(previous!=null) {
            var replay=command(wait,requestId,shell(original,previous.targetRevision(),previous.issuedAt(),previous.expiresAt()));
            if(!Arrays.equals(previous.waitEventId(),bytes(wait.waitEventId()))||!previous.requestHash().equals(replay.canonicalFingerprint())
                ||!previous.candidateDigest().equals(replay.refreshedContext().authorization().packetDigest()))throw new MemoryException("MEMORY_RESUME_CONFLICT");
            return replay;
        }
        if(refresh.findPending(tenant,execution)!=null)throw new MemoryException("MEMORY_REFRESH_PENDING");
        if(wait.refreshCount()>=3||refresh.maxConfirmedCount(tenant,execution)>=3
                ||refresh.countForWait(tenant,execution,bytes(wait.waitEventId()))>=3)throw new MemoryException("CONTEXT_REFRESH_LIMIT");
        var current=refresh.findCurrent(tenant,execution);
        long currentRevision=current==null?row.packetRevision():current.targetRevision();
        if(wait.expectedPacketRevision()!=currentRevision||current!=null&&!wait.expectedCurrentContextFingerprint().equals(current.currentContextFingerprint()))
            throw new MemoryException("MEMORY_REVISION_CONFLICT");
        if(current!=null&&"APPLIED_EXPIRED".equals(current.phase())&&(current.nextWaitEventId()==null||!wait.waitEventId().equals(text(current.nextWaitEventId()))))
            throw new MemoryException("MEMORY_RESUME_CONFLICT");
        long now=clock.instant().getEpochSecond();
        long expires=Math.min(Math.min(anchor.originalDeadline(),anchor.sourceRetentionDeadline()),now+anchor.policyTtlSeconds());
        expires=Math.min(expires,dependencies.requireCurrent(scope,original.packet().safetyDependencies()).getEpochSecond());
        for(var item:original.packet().items()) {
            long itemExpiry=item.itemId().startsWith("share:")?sharingService.hydrate(actor,scope,item.itemId().substring(6)).expiresAt().getEpochSecond():preferences.get(actor,scope,item.itemId()).preference().expiresAt().getEpochSecond();
            expires=Math.min(expires,itemExpiry);
        }
        if(expires<=now)throw new MemoryException("MEMORY_EXECUTION_EXPIRED");
        long target=Math.max(currentRevision,refresh.highestRevision(tenant,execution))+1;
        var envelope=shell(original,target,now,expires);var request=command(wait,requestId,envelope);
        var old=shell(original,currentRevision,original.packet().issuedAt(),original.packet().expiresAt());
        try {request.validateBinding(wait,original.scope(),wait.executionId(),wait.expectedCurrentContextFingerprint(),old);}
        catch(IllegalArgumentException failure){throw new MemoryException(failure.getMessage());}
        var candidate=new MemoryRefreshMapper.Candidate(tenant,execution,bytes(requestId),bytes(wait.waitEventId()),currentRevision,target,
            wait.expectedCurrentContextFingerprint(),request.canonicalFingerprint(),envelope.authorization().packetDigest(),now,expires,"PREPARED",
            null,null,null,null,null,null,null,null,false);
        if(refresh.insertCandidate(anchor,candidate)!=1)throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
        return request;
    }
    private static MemoryResumeRequest command(MemoryContextWait wait,String requestId,MemoryContextEnvelope envelope) {
        return new MemoryResumeRequest(wait.waitEventId(),wait.expectedPacketRevision(),wait.expectedExecutionRevision(),requestId,
            wait.operationHash(),MemoryResumeRequest.Mode.refresh,false,"memory-context-resume/2",wait.logicalOperationId(),
            wait.canonicalRequestHmac(),wait.attempt(),wait.expectedCurrentContextFingerprint(),envelope);
    }
    private static MemoryContextEnvelope shell(MemoryContextEnvelope original,long revision,long issued,long expires) {
        var p=original.packet();var a=original.authorization();
        var packet=new MemoryContextPacket(p.packetId(),revision,p.scope(),p.taskId(),p.executionId(),p.policyVersion(),p.executionRevision(),
            issued,expires,p.grantEpoch(),p.sourceEpoch(),p.deletionEpoch(),p.semanticInputHash(),p.parentAuthorizationRef(),p.items(),p.safetyDependencies());
        return new MemoryContextEnvelope(original.schemaVersion(),original.memoryMode(),original.scope(),packet,
            new MemoryAuthorization(a.policy(),a.executionGrants(),a.deadlineEpochSeconds(),MemoryPacketDigest.digest(packet),a.semanticSnapshotDigest(),a.requestDigest(),a.inputDependencies(),a.summaryContextJson(),a.deriveTemplateJson(),a.knowledgeContextJson()));
    }
    /** 回执须绑定已提交的完整请求；PENDING不改变本地候选，终态不可覆盖。 */
    public MemoryResumeReceipt recordReceipt(String tenantId,String executionId,MemoryResumeRequest request,MemoryResumeReceipt receipt) {
        requireRefresh();try {return transactions.execute(status->{
            var candidate=refresh.findCandidate(bytes(tenantId),bytes(executionId),bytes(request.resumeRequestId()));
            if(candidate==null||!candidate.requestHash().equals(request.canonicalFingerprint())||receipt==null||receipt.state()==null
                ||!request.waitEventId().equals(receipt.waitEventId())||receipt.packetRevision()==null||receipt.packetRevision()!=candidate.targetRevision()
                ||receipt.executionRevision()==null||receipt.executionRevision()!=request.expectedExecutionRevision()||receipt.candidatePhase()==null)
                throw new MemoryException("MEMORY_RESUME_CONFLICT");
            if(!"PREPARED".equals(candidate.phase())) {
                if(!receipt.equals(receipt(candidate,request.expectedExecutionRevision())))throw new MemoryException("MEMORY_RESUME_CONFLICT");
                return receipt;
            }
            if(receipt.candidatePhase()==MemoryResumeReceipt.CandidatePhase.PENDING)return receipt;
            if(receipt.candidatePhase()==MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED
                &&(receipt.currentPacketRevision()!=candidate.oldPacketRevision()||!candidate.expectedCurrentContextFingerprint().equals(receipt.currentContextFingerprint())))
                throw new MemoryException("MEMORY_RESUME_CONFLICT");
            if(refresh.complete(candidate,receipt)!=1)throw new MemoryException("MEMORY_RESUME_CONFLICT");return receipt;
        });}catch(org.springframework.dao.DataAccessException failure){throw new MemoryException("MEMORY_REFRESH_SCHEMA_REQUIRED");}
    }
    private static MemoryResumeReceipt receipt(MemoryRefreshMapper.Candidate c,long executionRevision) {
        return new MemoryResumeReceipt(MemoryResumeReceipt.Code.valueOf(c.receiptCode()),text(c.receiptRef()),text(c.waitEventId()),c.targetRevision(),
            executionRevision,c.currentPacketRevision(),c.currentContextFingerprint(),c.refreshCount(),MemoryResumeReceipt.State.valueOf(c.receiptState()),
            MemoryResumeReceipt.CandidatePhase.valueOf(c.candidatePhase()),c.nextWaitEventId()==null?null:text(c.nextWaitEventId()),c.dispatchAllowed());
    }
    /** 技术当前版本不能代替实时发送许可；候选过期始终不可用。 */
    public record CurrentAuthorization(long packetRevision,String contextFingerprint,boolean dispatchAllowed) {}
    public CurrentAuthorization currentAuthorization(String tenantId,String executionId) {
        requireRefresh();var row=packets.findPacket(bytes(tenantId),bytes(executionId));
        if(row==null)throw new MemoryException("MEMORY_AUTHORITY_UNAVAILABLE");
        var current=refresh.findCurrent(bytes(tenantId),bytes(executionId));
        return new CurrentAuthorization(current==null?row.packetRevision():current.targetRevision(),current==null?null:current.currentContextFingerprint(),false);
    }
    private static byte[] bytes(String value) { return MemoryMapper.identity(value); }
    private boolean validInputClosure(MemoryScopeDTO scope,MemoryPacketMapper.PacketRow issued,
            com.aiep.platformai.api.dto.MemoryRuntimeManifest.Operation operation,List<MemoryContextPacket.Dependency> required) {
        if(operation.safetyDependencies().containsAll(required))return true;
        if(!"operations".equals(scope.domain())||!MemoryAgentPolicyService.OPERATION_EXPERTS.contains(operation.scope().executionAgentId())
                ||operation.safetyDependencies().isEmpty()||operation.safetyDependencies().stream().noneMatch(dep->"CURRENT_USER_MESSAGE".equals(dep.sourceType())))return false;
        try {
            var policy=JSON.readValue(issued.policyJson(),MemoryAuthorization.Policy.class);
            var published=memory.findPolicyVersion(issued.tenantId(),bytes(policy.policyId()),bytes(policy.version()));
            var flag=published==null?null:JSON.readTree(published.policyJson()).path("context").get("specialistLineageEnabled");
            return flag!=null&&flag.isBoolean()&&flag.booleanValue();
        }catch(java.io.IOException invalid){return false;}
    }
    private void validateSharingDependencies(IdentityFacade.Subject actor,MemoryScopeDTO scope,List<MemoryContextPacket.Dependency> closure) {
        for(var dependency:closure)if("MEMORY_SHARE_GRANT".equals(dependency.sourceType())) {
            if(sharingService==null||!sharingService.enabled())throw new MemoryException("MEMORY_SOURCE_CHANGED");
            sharingService.hydrate(actor,scope,dependency.sourceId());
        }
    }
    private static String text(byte[] value) { return new String(value, StandardCharsets.UTF_8); }
}
