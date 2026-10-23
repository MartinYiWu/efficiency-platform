package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionKnowledgeBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPolicyBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptBindingPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AiAgentManagementService {
    private static final String USER_ID = "1";
    private static final Map<String, String> NEXT_STATUS = Map.of(
            "DRAFT", "VALIDATED", "VALIDATED", "RELEASED", "RELEASED", "RETIRED");
    private final AiManagementMappers repository;

    public AiAgentManagementService(AiManagementMappers repository) {
        this.repository = repository;
    }

    public List<AgentDefinitionPO> list() {
        return repository.listAgents();
    }

    public AiManagementViews.AgentDetail get(String id) {
        AgentDefinitionPO definition = requiredAgent(id);
        return new AiManagementViews.AgentDetail(definition, repository.listAgentVersions(id), repository.listEvidenceBindings(id));
    }

    @Transactional
    public AgentDefinitionPO create(String agentKey, String name, String description, String agentType) {
        LocalDateTime now = LocalDateTime.now();
        AgentDefinitionPO value = new AgentDefinitionPO(
                UUID.randomUUID().toString(), required(agentKey, "Agent 编码"),
                required(name, "Agent 名称"), optional(description),
                required(agentType, "Agent 类型"), "ACTIVE", USER_ID, now, USER_ID, now);
        repository.insertAgent(value);
        return value;
    }

    @Transactional
    public AgentVersionPO createVersion(
            String agentId, String semanticVersion, String graphKey,
            String graphVersion, String changeSummary) {
        return createVersion(
                agentId, semanticVersion, graphKey, graphVersion, changeSummary, null);
    }

    @Transactional
    public AgentVersionPO createVersion(
            String agentId, String semanticVersion, String graphKey,
            String graphVersion, String changeSummary, String sourceVersionId) {
        requiredAgent(agentId);
        AgentVersionPO value = new AgentVersionPO(
                UUID.randomUUID().toString(), agentId, required(semanticVersion, "版本号"),
                required(graphKey, "Graph 编码"), required(graphVersion, "Graph 版本"),
                "DRAFT", required(changeSummary, "变更说明"), USER_ID,
                LocalDateTime.now(), null);
        repository.insertAgentVersion(value);
        if (sourceVersionId != null && !sourceVersionId.isBlank()) {
            cloneBindings(value, sourceVersionId.strip());
        }
        return value;
    }

    private void cloneBindings(AgentVersionPO target, String sourceVersionId) {
        AgentVersionPO source = requiredVersion(sourceVersionId);
        if (!target.agentDefinitionId().equals(source.agentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "源 Agent 版本归属不匹配");
        }
        AgentVersionPolicyBindingPO policies = repository.findPolicyBinding(sourceVersionId);
        if (policies != null) {
            if (policies.modelPolicyId() != null) {
                repository.upsertModelPolicyBinding(target.id(), policies.modelPolicyId());
            }
            if (policies.ragPolicyId() != null) {
                repository.upsertRagPolicyBinding(target.id(), policies.ragPolicyId());
            }
            if (policies.largeContextModelPolicyId() != null) {
                repository.upsertLargeContextModelPolicyBinding(target.id(), policies.largeContextModelPolicyId());
            }
        }
        for (PromptBindingPO binding : repository.listPromptBindings(sourceVersionId)) {
            repository.insertPromptBinding(new PromptBindingPO(
                    target.id(), binding.stageKey(), binding.ordinal(),
                    binding.promptDefinitionId(), binding.promptVersionId(), binding.required()));
        }
        List<AgentVersionKnowledgeBindingPO> knowledge = repository
                .listKnowledgeBindings(sourceVersionId).stream()
                .map(binding -> new AgentVersionKnowledgeBindingPO(
                        target.id(), binding.knowledgeBaseId(), binding.indexReleaseId(),
                        binding.priority(), binding.required()))
                .toList();
        if (!knowledge.isEmpty()) {
            repository.replaceKnowledgeBindings(target.id(), knowledge);
        }
    }

    @Transactional
    public AgentVersionPO updateDraft(
            String id, String semanticVersion, String graphKey,
            String graphVersion, String changeSummary) {
        AgentVersionPO current = requiredVersion(id);
        mutable(current.status());
        AgentVersionPO value = new AgentVersionPO(
                current.id(), current.agentDefinitionId(), required(semanticVersion, "版本号"),
                required(graphKey, "Graph 编码"), required(graphVersion, "Graph 版本"),
                current.status(), required(changeSummary, "变更说明"), current.createdBy(),
                current.createdAt(), current.publishedAt());
        repository.updateAgentVersion(value);
        return value;
    }

    @Transactional
    public AgentVersionPO transition(String id, String targetStatus) {
        AgentVersionPO current = requiredVersion(id);
        String target = required(targetStatus, "目标状态").toUpperCase();
        if (!target.equals(NEXT_STATUS.get(current.status()))) {
            throw new AiManagementException("AI_ASSET_STATE_INVALID", "Agent 版本状态流转无效");
        }
        AgentVersionPO value = new AgentVersionPO(
                current.id(), current.agentDefinitionId(), current.semanticVersion(),
                current.graphKey(), current.graphVersion(), target, current.changeSummary(),
                current.createdBy(), current.createdAt(),
                "RELEASED".equals(target) ? LocalDateTime.now() : current.publishedAt());
        repository.updateAgentVersion(value);
        return value;
    }

    @Transactional
    public AgentVersionPolicyBindingPO bindModelPolicy(String versionId, String modelPolicyId) {
        AgentVersionPO version = requiredVersion(versionId);
        mutable(version.status());
        ModelPolicyPO model = repository.findModelPolicy(modelPolicyId);
        if (model == null || !version.agentDefinitionId().equals(model.ownerAgentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "模型策略不属于该 Agent");
        }
        if (!"PUBLISHED".equals(model.status())) {
            throw new AiManagementException("AI_POLICY_NOT_PUBLISHED", "只能绑定已发布策略");
        }
        AgentVersionPolicyBindingPO binding = repository.findPolicyBinding(versionId);
        if (binding != null && binding.largeContextModelPolicyId() != null) {
            ModelPolicyPO large = repository.findModelPolicy(binding.largeContextModelPolicyId());
            if (large == null || large.maxInputTokens() <= model.maxInputTokens()) {
                throw new AiManagementException("AI_LARGE_MODEL_INPUT_INVALID", "备选模型输入上限必须严格大于主模型");
            }
        }
        repository.upsertModelPolicyBinding(versionId, modelPolicyId);
        return repository.findPolicyBinding(versionId);
    }

    @Transactional
    public AgentVersionPolicyBindingPO bindRagPolicy(String versionId, String ragPolicyId) {
        AgentVersionPO version = requiredVersion(versionId);
        mutable(version.status());
        RagPolicyPO rag = repository.findRagPolicy(ragPolicyId);
        if (rag == null || !version.agentDefinitionId().equals(rag.ownerAgentDefinitionId())) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "RAG 策略不属于该 Agent");
        }
        if (!"PUBLISHED".equals(rag.status())) {
            throw new AiManagementException("AI_POLICY_NOT_PUBLISHED", "只能绑定已发布策略");
        }
        repository.upsertRagPolicyBinding(versionId, ragPolicyId);
        return repository.findPolicyBinding(versionId);
    }

    @Transactional
    public AgentVersionPolicyBindingPO bindLargeContextModelPolicy(String versionId, String policyId) {
        AgentVersionPO version = requiredVersion(versionId);
        mutable(version.status());
        if (policyId != null) {
            ModelPolicyPO large = repository.findModelPolicy(required(policyId, "备选模型策略 ID"));
            if (large == null || !version.agentDefinitionId().equals(large.ownerAgentDefinitionId())) {
                throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "模型策略不属于该 Agent");
            }
            if (!"PUBLISHED".equals(large.status())) {
                throw new AiManagementException("AI_POLICY_NOT_PUBLISHED", "只能绑定已发布策略");
            }
            AgentVersionPolicyBindingPO binding = repository.findPolicyBinding(versionId);
            ModelPolicyPO primary = binding == null || binding.modelPolicyId() == null
                    ? null : repository.findModelPolicy(binding.modelPolicyId());
            if (primary == null || large.maxInputTokens() <= primary.maxInputTokens()) {
                throw new AiManagementException("AI_LARGE_MODEL_INPUT_INVALID", "备选模型输入上限必须严格大于已绑定主模型");
            }
        }
        repository.upsertLargeContextModelPolicyBinding(versionId, policyId);
        return repository.findPolicyBinding(versionId);
    }

    @Transactional
    public List<AgentVersionKnowledgeBindingPO> bindKnowledge(
            String versionId, List<KnowledgeBindingInput> inputs) {
        AgentVersionPO version = requiredVersion(versionId);
        mutable(version.status());
        List<AgentVersionKnowledgeBindingPO> values = inputs.stream()
                .map(input -> {
                    if (input.priority() <= 0) {
                        throw new AiManagementException(
                                "AI_KNOWLEDGE_BINDING_PRIORITY_INVALID", "知识绑定优先级必须大于 0");
                    }
                    if (!repository.isIndexReleaseReady(input.indexReleaseId())) {
                        throw new AiManagementException(
                                "AI_INDEX_RELEASE_NOT_READY", "知识索引未发布");
                    }
                    return new AgentVersionKnowledgeBindingPO(
                            versionId, required(input.knowledgeBaseId(), "知识库 ID"),
                            required(input.indexReleaseId(), "索引版本 ID"),
                            input.priority(), input.required());
                }).toList();
        repository.replaceKnowledgeBindings(versionId, values);
        return values;
    }

    private AgentDefinitionPO requiredAgent(String id) {
        AgentDefinitionPO value = repository.findAgent(id);
        if (value == null) {
            throw new AiManagementException("AI_AGENT_NOT_FOUND", "Agent 不存在");
        }
        return value;
    }

    private AgentVersionPO requiredVersion(String id) {
        AgentVersionPO value = repository.findAgentVersion(id);
        if (value == null) {
            throw new AiManagementException("AI_AGENT_VERSION_NOT_FOUND", "Agent 版本不存在");
        }
        return value;
    }

    static void mutable(String status) {
        if (!"DRAFT".equals(status)) {
            throw new AiManagementException("AI_ASSET_IMMUTABLE", "仅草稿资产允许修改");
        }
    }

    static String required(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new AiManagementException("AI_ASSET_FIELD_REQUIRED", label + "不能为空");
        }
        return value.strip();
    }

    private static String optional(String value) {
        return value == null || value.isBlank() ? null : value.strip();
    }

    public record KnowledgeBindingInput(
            String knowledgeBaseId, String indexReleaseId, int priority, boolean required) { }
}
