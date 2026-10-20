package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionKnowledgeBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptMessageTemplatePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVariablePO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.aihub.repository.management.AiReleaseSnapshotPO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceReleaseAck;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.KnowledgeBinding;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.ModelPolicy;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.PromptBinding;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.PromptMessage;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.PromptVariable;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest.RagPolicy;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class AiReleaseService {
    private static final String USER_ID = "1";
    private final AiManagementMappers repository;
    private final AiInvokeFacade ai;
    private final ObjectMapper objectMapper;

    public AiReleaseService(
            AiManagementMappers repository, AiInvokeFacade ai, ObjectMapper objectMapper) {
        this.repository = repository;
        this.ai = ai;
        this.objectMapper = objectMapper;
    }

    public AiReleasePO publish(String agentVersionId, String environment) {
        AgentVersionPO version = requiredVersion(agentVersionId);
        if (!"VALIDATED".equals(version.status())) {
            throw new AiManagementException("AI_AGENT_VERSION_NOT_VALIDATED", "Agent 版本必须先通过校验");
        }
        CustomerServiceReleaseRequest request = buildRequest(version, environment);
        return deliver(version, request, null);
    }

    public AiReleasePO publish(String agentKey, String agentVersionId, String environment) {
        AgentDefinitionPO definition = repository.findAgentByKey(agentKey);
        AgentVersionPO version = requiredVersion(agentVersionId);
        if (definition == null || !definition.id().equals(version.agentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "Agent Version 归属不匹配");
        }
        return publish(agentVersionId, environment);
    }

    public AiReleasePO rollback(String targetReleaseId) {
        AiReleasePO target = repository.findRelease(targetReleaseId);
        AiReleaseSnapshotPO snapshot = repository.findReleaseSnapshot(targetReleaseId);
        if (target == null || snapshot == null || !"ACKNOWLEDGED".equals(snapshot.agentAckStatus())) {
            throw new AiManagementException("AI_RELEASE_NOT_FOUND", "可回滚 Release 不存在");
        }
        try {
            CustomerServiceReleaseRequest request = objectMapper.readValue(
                    snapshot.snapshotJson(), CustomerServiceReleaseRequest.class);
            return deliver(requiredVersion(target.agentVersionId()), request, targetReleaseId);
        } catch (JsonProcessingException exception) {
            throw new AiManagementException("AI_RELEASE_SNAPSHOT_INVALID", "Release 快照无法读取");
        }
    }

    public AiReleasePO rollback(String agentKey, String targetReleaseId) {
        AgentDefinitionPO definition = repository.findAgentByKey(agentKey);
        AiReleasePO target = repository.findRelease(targetReleaseId);
        if (definition == null || target == null
                || !definition.id().equals(target.agentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "Release 归属不匹配");
        }
        return rollback(targetReleaseId);
    }

    public List<AiReleasePO> list(String agentKey, String environment) {
        AgentDefinitionPO definition = repository.findAgentByKey(agentKey);
        if (definition == null) {
            throw new AiManagementException("AI_AGENT_NOT_FOUND", "Agent 不存在");
        }
        return repository.listReleases(
                definition.id(), AiAgentManagementService.required(environment, "发布环境"));
    }

    public AiReleasePO active(String agentDefinitionId, String environment) {
        return repository.findActiveRelease(agentDefinitionId, environment);
    }

    private AiReleasePO deliver(
            AgentVersionPO version, CustomerServiceReleaseRequest request,
            String rolledBackFromReleaseId) {
        String releaseId = UUID.randomUUID().toString();
        String snapshotId = UUID.randomUUID().toString();
        LocalDateTime now = LocalDateTime.now();
        AiReleasePO pending = new AiReleasePO(
                releaseId, version.agentDefinitionId(), version.id(), request.environment(),
                "PENDING", snapshotId, USER_ID, null, rolledBackFromReleaseId, now);
        AiReleaseSnapshotPO snapshot = new AiReleaseSnapshotPO(
                snapshotId, releaseId, json(request), request.snapshotChecksum(),
                "PENDING", null, now);
        repository.insertRelease(pending, snapshot);
        CustomerServiceReleaseAck ack = ai.publishCustomerServiceRelease(releaseId, request);
        if (!releaseId.equals(ack.releaseId())
                || !request.snapshotChecksum().equals(ack.checksum())) {
            throw new AiManagementException("AI_RELEASE_ACK_MISMATCH", "Agent Release 确认不匹配");
        }
        repository.acknowledgeAndActivateRelease(
                releaseId, snapshotId, version.agentDefinitionId(),
                request.environment(), version.id());
        return new AiReleasePO(
                releaseId, version.agentDefinitionId(), version.id(), request.environment(),
                "ACTIVE", snapshotId, USER_ID, LocalDateTime.now(),
                rolledBackFromReleaseId, now);
    }

    private CustomerServiceReleaseRequest buildRequest(
            AgentVersionPO version, String environment) {
        AgentDefinitionPO agent = repository.findAgent(version.agentDefinitionId());
        if (agent == null || !"customer-service".equals(agent.agentKey())) {
            throw new AiManagementException("AI_RELEASE_AGENT_INVALID", "只能发布独立智能客服 Agent");
        }
        AgentVersionPolicyBindingPO policyBinding = repository.findPolicyBinding(version.id());
        if (policyBinding == null || policyBinding.modelPolicyId() == null
                || policyBinding.ragPolicyId() == null) {
            throw new AiManagementException("AI_RELEASE_POLICY_REQUIRED", "模型和 RAG 策略未绑定");
        }
        ModelPolicyPO model = repository.findModelPolicy(policyBinding.modelPolicyId());
        RagPolicyPO rag = repository.findRagPolicy(policyBinding.ragPolicyId());
        validatePolicies(version.agentDefinitionId(), model, rag);

        List<PromptBinding> prompts = repository.listPromptBindings(version.id()).stream()
                .map(value -> prompt(version.agentDefinitionId(), value))
                .sorted(Comparator.comparing(PromptBinding::stageKey)
                        .thenComparingInt(PromptBinding::ordinal))
                .toList();
        if (prompts.isEmpty()) {
            throw new AiManagementException("AI_RELEASE_PROMPT_REQUIRED", "Prompt 绑定为空");
        }
        List<KnowledgeBinding> knowledge = repository.listKnowledgeBindings(version.id()).stream()
                .map(this::knowledge)
                .sorted(Comparator.comparingInt(KnowledgeBinding::priority)
                        .thenComparing(KnowledgeBinding::knowledgeBaseId))
                .toList();
        if (knowledge.isEmpty()) {
            throw new AiManagementException("AI_RELEASE_KNOWLEDGE_REQUIRED", "知识索引绑定为空");
        }
        CustomerServiceReleaseRequest provisional = new CustomerServiceReleaseRequest(
                "customer-service-release/1", "customer-service", version.semanticVersion(),
                version.graphKey(), version.graphVersion(),
                AiAgentManagementService.required(environment, "发布环境"), prompts,
                model(model), rag(rag), knowledge, List.of(),
                "customer-service-answer/1", "1", "0".repeat(64));
        String checksum = checksum(provisional);
        return new CustomerServiceReleaseRequest(
                provisional.contractVersion(), provisional.agentKey(), provisional.agentVersion(),
                provisional.graphKey(), provisional.graphVersion(), provisional.environment(),
                provisional.promptBindings(), provisional.modelPolicy(), provisional.ragPolicy(),
                provisional.knowledgeBindings(), provisional.toolAllowlist(),
                provisional.outputContractVersion(), provisional.safetyRuleVersion(), checksum);
    }

    private PromptBinding prompt(String agentId, PromptBindingPO binding) {
        PromptDefinitionPO definition = repository.findPromptDefinition(binding.promptDefinitionId());
        PromptVersionPO version = repository.findPromptVersion(binding.promptVersionId());
        if (definition == null || version == null || !"PUBLISHED".equals(version.status())) {
            throw new AiManagementException("AI_RELEASE_PROMPT_INVALID", "Prompt 版本未发布");
        }
        if ("PRIVATE".equals(definition.scope())
                && !agentId.equals(definition.ownerAgentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "私有 Prompt 归属不匹配");
        }
        List<PromptVariablePO> variables = repository.listPromptVariables(version.id());
        Map<String, List<PromptVariable>> byMessage = new LinkedHashMap<>();
        for (PromptVariablePO value : variables) {
            byMessage.computeIfAbsent(value.promptMessageTemplateId(), ignored -> new ArrayList<>())
                    .add(new PromptVariable(
                            value.variableName(), value.valueType(), value.valueSource(),
                            value.required(), value.sensitive(), value.maxLength(),
                            value.allowUntrustedContent()));
        }
        List<PromptMessage> messages = repository.listPromptMessages(version.id()).stream()
                .sorted(Comparator.comparingInt(PromptMessageTemplatePO::ordinal))
                .map(value -> new PromptMessage(
                        value.ordinal(), value.role(), value.messageKey(), value.contentTemplate(),
                        value.contentFormat(), value.trustedInstruction(), value.checksum(),
                        List.copyOf(byMessage.getOrDefault(value.id(), List.of()))))
                .toList();
        if (messages.isEmpty()) {
            throw new AiManagementException("AI_RELEASE_PROMPT_INVALID", "Prompt 消息为空");
        }
        return new PromptBinding(
                binding.stageKey(), binding.ordinal(), definition.promptKey(),
                version.semanticVersion(), version.checksum(), messages);
    }

    private KnowledgeBinding knowledge(AgentVersionKnowledgeBindingPO value) {
        if (!repository.isIndexReleaseReady(value.indexReleaseId())) {
            throw new AiManagementException("AI_INDEX_RELEASE_NOT_READY", "知识索引未发布");
        }
        return new KnowledgeBinding(
                value.knowledgeBaseId(), value.indexReleaseId(), value.priority(), value.required());
    }

    private static void validatePolicies(
            String agentId, ModelPolicyPO model, RagPolicyPO rag) {
        if (model == null || rag == null || !agentId.equals(model.ownerAgentDefinitionId())
                || !agentId.equals(rag.ownerAgentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "策略归属不匹配");
        }
        if (!"PUBLISHED".equals(model.status()) || !"PUBLISHED".equals(rag.status())) {
            throw new AiManagementException("AI_POLICY_NOT_PUBLISHED", "策略未发布");
        }
    }

    private static ModelPolicy model(ModelPolicyPO value) {
        return new ModelPolicy(
                value.policyKey(), value.semanticVersion(), value.provider(), value.modelName(),
                normalize(value.temperature()), normalize(value.topP()), value.maxInputTokens(),
                value.maxOutputTokens(), value.connectTimeoutMs(), value.readTimeoutMs(),
                value.maxRetries(), value.checksum());
    }

    private static RagPolicy rag(RagPolicyPO value) {
        return new RagPolicy(
                value.policyKey(), value.semanticVersion(), value.rewriteQueryLimit(),
                value.vectorTopK(), value.ftsTopK(), value.fusionTopK(), value.rerankTopK(),
                value.contextTokenLimit(), value.citationLimit(), value.checksum());
    }

    private AgentVersionPO requiredVersion(String id) {
        AgentVersionPO value = repository.findAgentVersion(id);
        if (value == null) {
            throw new AiManagementException("AI_AGENT_VERSION_NOT_FOUND", "Agent 版本不存在");
        }
        return value;
    }

    private String checksum(CustomerServiceReleaseRequest request) {
        JsonNode tree = objectMapper.valueToTree(request);
        ((com.fasterxml.jackson.databind.node.ObjectNode) tree).remove("snapshot_checksum");
        try {
            byte[] canonical = objectMapper.writeValueAsBytes(canonical(tree));
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical));
        } catch (JsonProcessingException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("无法生成 Release checksum", exception);
        }
    }

    private Object canonical(JsonNode node) {
        if (node.isObject()) {
            Map<String, Object> value = new TreeMap<>();
            node.fields().forEachRemaining(entry -> value.put(entry.getKey(), canonical(entry.getValue())));
            return value;
        }
        if (node.isArray()) {
            List<Object> value = new ArrayList<>();
            node.forEach(item -> value.add(canonical(item)));
            return value;
        }
        if (node.isIntegralNumber()) {
            return node.longValue();
        }
        if (node.isFloatingPointNumber()) {
            return node.decimalValue().stripTrailingZeros();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        if (node.isNull()) {
            return null;
        }
        return node.textValue();
    }

    private String json(CustomerServiceReleaseRequest request) {
        try {
            return objectMapper.writeValueAsString(request);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("无法保存 Release 快照", exception);
        }
    }

    private static BigDecimal normalize(BigDecimal value) {
        return value.stripTrailingZeros();
    }
}
