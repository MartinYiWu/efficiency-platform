package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
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

    @Autowired public MemoryPacketService(@Value("${aiep.memory.packet-enabled:false}") boolean enabled,
            MemoryMapper memory, MemoryPacketMapper packets, MemoryScopePolicy scopes,
            MemorySessionBindingService bindings, MemoryPolicyService policies, MemoryPreferenceService preferences,
            MemoryDependencyService dependencies, MemoryValueCodec codec, PlatformTransactionManager manager) {
        this(enabled, memory, packets, scopes, bindings, policies, preferences, dependencies, codec, manager, Clock.systemUTC());
    }
    public MemoryPacketService(boolean enabled, MemoryMapper memory, MemoryPacketMapper packets, MemoryScopePolicy scopes,
            MemorySessionBindingService bindings, MemoryPolicyService policies, MemoryPreferenceService preferences,
            MemoryDependencyService dependencies, MemoryValueCodec codec, PlatformTransactionManager manager, Clock clock) {
        this.enabled=enabled; this.memory=memory; this.packets=packets; this.scopes=scopes; this.bindings=bindings;
        this.policies=policies; this.preferences=preferences; this.dependencies=dependencies; this.codec=codec;
        this.transactions=new TransactionTemplate(manager); this.clock=clock;
    }
    public boolean enabled() { return enabled; }

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
                || !text(issued.packetId()).equals(manifest.packetId()) || issued.packetRevision()!=manifest.packetRevision()
                || manifest.manifests().isEmpty()) throw new MemoryException("MEMORY_MANIFEST_BINDING_INVALID");
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
                if(!opScope.conversation().equals(originalScope)||!opScope.taskId().equals(text(issued.taskId()))
                    ||!opScope.executionId().equals(executionId)||!operation.packetId().equals(manifest.packetId())
                    ||operation.packetRevision()!=issued.packetRevision()
                    ||grants.stream().noneMatch(grant->grant.nodeId().equals(operation.nodeId())&&grant.executionAgentId().equals(opScope.executionAgentId())&&grant.purpose().equals(opScope.purpose()))
                    ||!allowed.containsAll(operation.safetyDependencies())
                    ||!operation.safetyDependencies().containsAll(inputDependencies)
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
                return issue(actor, scope, javaRunId, javaRunId, actualRequest, clock.instant().getEpochSecond()+timeout, all);
            });
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | java.security.NoSuchAlgorithmException failure) { throw new MemoryException("MEMORY_POLICY_INVALID"); }
    }

    public MemoryContextEnvelope issue(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId, String executionId,
            JsonNode actualRequest, long originalDeadline, List<MemoryContextPacket.Dependency> actualInputDependencies) {
        if (!enabled) return new ConversationScopeResolver().envelope(scope);
        scopes.require(actor, scope, Set.of()); bindings.require(actor, scope); codec.currentVersion();
        MemoryMapper.identity(taskId); MemoryMapper.identity(executionId);
        if (actualRequest == null || !actualRequest.isObject() || actualInputDependencies.isEmpty())
            throw new MemoryException("MEMORY_CURRENT_INPUT_DEPENDENCIES_REQUIRED");
        ObjectNode request = actualRequest.deepCopy(); request.remove("memory_context");
        String requestDigest = MemoryPacketDigest.canonicalDigest(request);
        try {
            return transactions.execute(status -> issueTransaction(actor, scope, taskId, executionId, requestDigest, originalDeadline, actualInputDependencies));
        } catch (DuplicateKeyException conflict) {
            return transactions.execute(status -> {
                var original = packets.findPacket(bytes(scope.tenantId()), bytes(executionId));
                if (original == null) throw new MemoryException("MEMORY_EXECUTION_CONFLICT");
                return restore(actor, scope, taskId, requestDigest, original);
            });
        }
    }

    private MemoryContextEnvelope issueTransaction(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId,
            String executionId, String requestDigest, long deadline, List<MemoryContextPacket.Dependency> actualInputs) {
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
            for (var preference : selected) {
                var closure = dependencies.dependencies(scope, "MEMORY_VERSION", preference.id(), preference.versionId());
                if (closure.isEmpty()) throw new MemoryException("MEMORY_SOURCE_CHANGED");
                items.add(new MemoryContextPacket.Item(preference.id(), preference.versionId(), preference.fieldKey(), preference.value(), closure));
                all.addAll(closure); expiry = Math.min(expiry, preference.expiresAt().getEpochSecond());
            }
            var closure = MemoryPacketDigest.dependencies(all);
            var sourceTypes = JSON.convertValue(context.path("sourceTypes"), new TypeReference<List<String>>(){});
            if (sourceTypes == null || sourceTypes.isEmpty() || closure.stream().anyMatch(dep -> !sourceTypes.contains(dep.sourceType())))
                throw new MemoryException("MEMORY_SOURCE_TYPE_DENIED");
            expiry = Math.min(expiry, dependencies.requireCurrent(scope, closure).getEpochSecond());
            if (expiry <= now) throw new MemoryException("MEMORY_SOURCE_CHANGED");
            var policy = new MemoryAuthorization.Policy(text(published.id()), text(published.versionId()), scope.domain(),
                    List.copyOf(agents), true, List.of("semantic"), List.of(), List.of("USER_PRIVATE"), List.copyOf(fields),
                    List.of("LOW"), true, false, true, sourceTypes,
                    0, 0, 0, 0, "disabled", "block", "1", "none", "none");
            var neutralScope = new MemoryContextEnvelope.Scope(scope.tenantId(), scope.userId(), scope.domain(), scope.topLevelAgentId(), scope.sessionKind(), scope.sessionId());
            var packet = new MemoryContextPacket(UUID.randomUUID().toString(), 1, neutralScope, taskId, executionId,
                    policy.version(), 1, now, expiry, 0, 0, 0, requestDigest, executionId, items, closure);
            var refs = JSON.valueToTree(items);
            refs.forEach(item -> ((ObjectNode) item).remove("value"));
            var referenceSnapshot=JSON.createObjectNode();referenceSnapshot.put("schema_version","memory-packet-references/2");referenceSnapshot.set("items",refs);
            referenceSnapshot.set("input_dependencies",JSON.valueToTree(MemoryPacketDigest.dependencies(actualInputs)));
            var row = new MemoryPacketMapper.PacketRow(bytes(scope.tenantId()), bytes(executionId), bytes(packet.packetId()), 1,
                    bytes(scope.userId()), bytes(taskId), JSON.writeValueAsString(neutralScope), JSON.writeValueAsString(policy),
                    JSON.writeValueAsString(grants), JSON.writeValueAsString(referenceSnapshot), JSON.writeValueAsString(closure), requestDigest,
                    MemoryPacketDigest.digest(packet), MemoryPacketDigest.semanticDigest(packet), requestDigest, bytes(executionId),
                    1, 0, 0, 0, deadline, now, expiry);
            if (packets.insertPacket(row) != 1) throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");
            dependencies.record(scope, "EXECUTION", executionId, "1", executionId, closure, List.of(closure), List.of());
            return new MemoryContextEnvelope("memory-context/1", "EXACT_ONLY", neutralScope, packet,
                    new MemoryAuthorization(policy, grants, deadline, row.packetDigest(), row.semanticDigest(), requestDigest,MemoryPacketDigest.dependencies(actualInputs)));
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | IllegalArgumentException failure) { throw new MemoryException("MEMORY_POLICY_INVALID"); }
    }

    private MemoryContextEnvelope restore(IdentityFacade.Subject actor, MemoryScopeDTO scope, String taskId,
            String requestDigest, MemoryPacketMapper.PacketRow row) {
        if (!Arrays.equals(bytes(scope.userId()), row.userId()) || !Arrays.equals(bytes(taskId), row.taskId())
                || !requestDigest.equals(row.requestDigest())) throw new MemoryException("MEMORY_EXECUTION_CONFLICT");
        if (clock.instant().getEpochSecond() >= Math.min(row.expiresAt(), row.originalDeadline())) throw new MemoryException("MEMORY_EXECUTION_EXPIRED");
        try {
            var neutralScope = JSON.readValue(row.scopeJson(), MemoryContextEnvelope.Scope.class);
            if (!JSON.valueToTree(scope).equals(JSON.valueToTree(neutralScope))) throw new MemoryException("MEMORY_SCOPE_DENIED");
            var policy = JSON.readValue(row.policyJson(), MemoryAuthorization.Policy.class);
            MemoryPolicyService.requireArtifactPolicy(memory.findPolicyVersion(bytes(scope.tenantId()),bytes(policy.policyId()),bytes(policy.version())));
            var grants = JSON.readValue(row.grantsJson(), new TypeReference<List<MemoryAuthorization.ExecutionGrant>>(){});
            var closure = JSON.readValue(row.dependenciesJson(), new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            dependencies.requireCurrent(scope, closure);
            var items = new ArrayList<MemoryContextPacket.Item>();
            var referenceSnapshot=JSON.readTree(row.referencesJson());
            if(!"memory-packet-references/2".equals(referenceSnapshot.path("schema_version").asText())||!referenceSnapshot.path("items").isArray()||!referenceSnapshot.path("input_dependencies").isArray())throw new MemoryException("MEMORY_SOURCE_CHANGED");
            var inputDependencies=JSON.convertValue(referenceSnapshot.path("input_dependencies"),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
            var artifactVersions=new ArrayList<MemoryMapper.VersionIdentityPO>();
            for(var ref:referenceSnapshot.path("items"))artifactVersions.add(new MemoryMapper.VersionIdentityPO(bytes(ref.path("item_id").asText()),bytes(ref.path("version").asText())));
            policies.requireVersionArtifacts(bytes(scope.tenantId()),artifactVersions);
            for (var ref : referenceSnapshot.path("items")) {
                var live = preferences.get(actor, scope, ref.path("item_id").asText()).preference();
                if (!live.versionId().equals(ref.path("version").asText()) || !live.fieldKey().equals(ref.path("field_key").asText()))
                    throw new MemoryException("MEMORY_SOURCE_CHANGED");
                var deps = JSON.convertValue(ref.path("safety_dependencies"), new TypeReference<List<MemoryContextPacket.Dependency>>(){});
                items.add(new MemoryContextPacket.Item(live.id(), live.versionId(), live.fieldKey(), live.value(), deps));
            }
            var packet = new MemoryContextPacket(text(row.packetId()), row.packetRevision(), neutralScope, text(row.taskId()),
                    text(row.executionId()), policy.version(), row.executionRevision(), row.issuedAt(), row.expiresAt(),
                    row.grantEpoch(), row.sourceEpoch(), row.deletionEpoch(), row.semanticInputHash(), text(row.parentAuthorizationRef()), items, closure);
            return new MemoryContextEnvelope("memory-context/1", "EXACT_ONLY", neutralScope, packet,
                    new MemoryAuthorization(policy, grants, row.originalDeadline(), row.packetDigest(), row.semanticDigest(), row.requestDigest(),inputDependencies));
        } catch (MemoryException failure) { throw failure; }
        catch (java.io.IOException | IllegalArgumentException failure) { throw new MemoryException("MEMORY_SOURCE_CHANGED"); }
    }
    private static byte[] bytes(String value) { return MemoryMapper.identity(value); }
    private static String text(byte[] value) { return new String(value, StandardCharsets.UTF_8); }
}
