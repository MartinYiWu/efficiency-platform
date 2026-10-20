package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentVersionPO;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@ConditionalOnBean(JdbcTemplate.class)
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
        return new AiManagementViews.AgentDetail(definition, repository.listAgentVersions(id));
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
        requiredAgent(agentId);
        AgentVersionPO value = new AgentVersionPO(
                UUID.randomUUID().toString(), agentId, required(semanticVersion, "版本号"),
                required(graphKey, "Graph 编码"), required(graphVersion, "Graph 版本"),
                "DRAFT", required(changeSummary, "变更说明"), USER_ID,
                LocalDateTime.now(), null);
        repository.insertAgentVersion(value);
        return value;
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
}
