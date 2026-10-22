package com.aiep.aihub.application.management;

import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.ModelPolicyPO;
import com.aiep.aihub.repository.management.AiManagementPOs.RagPolicyPO;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AiPolicyManagementService {
    private static final String USER_ID = "1";
    private final AiManagementMappers repository;

    public AiPolicyManagementService(AiManagementMappers repository) {
        this.repository = repository;
    }

    public AiManagementViews.PolicyList list(String agentId) {
        return new AiManagementViews.PolicyList(
                repository.listModelPolicies(agentId), repository.listRagPolicies(agentId));
    }

    public ModelPolicyPO getModelPolicy(String agentId, String id) {
        ModelPolicyPO value = repository.findModelPolicy(id);
        if (value == null) {
            throw new AiManagementException("AI_MODEL_POLICY_NOT_FOUND", "模型策略不存在");
        }
        assertOwner(agentId, value.ownerAgentDefinitionId());
        return value;
    }

    public RagPolicyPO getRagPolicy(String agentId, String id) {
        RagPolicyPO value = repository.findRagPolicy(id);
        if (value == null) {
            throw new AiManagementException("AI_RAG_POLICY_NOT_FOUND", "RAG 策略不存在");
        }
        assertOwner(agentId, value.ownerAgentDefinitionId());
        return value;
    }

    @Transactional
    public ModelPolicyPO saveModel(ModelPolicyInput input) {
        ModelPolicyPO current = input.id() == null ? null : repository.findModelPolicy(input.id());
        if (current != null) {
            AiAgentManagementService.mutable(current.status());
            assertOwner(input.ownerAgentId(), current.ownerAgentDefinitionId());
        }
        LocalDateTime now = LocalDateTime.now();
        ModelPolicyPO value = new ModelPolicyPO(
                current == null ? UUID.randomUUID().toString() : current.id(),
                AiAgentManagementService.required(input.ownerAgentId(), "Agent ID"),
                AiAgentManagementService.required(input.policyKey(), "模型策略编码"),
                AiAgentManagementService.required(input.semanticVersion(), "版本号"),
                AiAgentManagementService.required(input.provider(), "模型供应商"),
                AiAgentManagementService.required(input.modelName(), "模型名称"),
                input.temperature(), input.topP(), input.maxInputTokens(), input.maxOutputTokens(),
                input.connectTimeoutMs(), input.readTimeoutMs(), input.maxRetries(), "DRAFT",
                AiAgentManagementService.required(input.checksum(), "校验和"), USER_ID,
                current == null ? now : current.createdAt(), null);
        if (current == null) {
            repository.insertModelPolicy(value);
        } else {
            repository.updateModelPolicy(value);
        }
        return value;
    }

    @Transactional
    public RagPolicyPO saveRag(RagPolicyInput input) {
        RagPolicyPO current = input.id() == null ? null : repository.findRagPolicy(input.id());
        if (current != null) {
            AiAgentManagementService.mutable(current.status());
            assertOwner(input.ownerAgentId(), current.ownerAgentDefinitionId());
        }
        LocalDateTime now = LocalDateTime.now();
        RagPolicyPO value = new RagPolicyPO(
                current == null ? UUID.randomUUID().toString() : current.id(),
                AiAgentManagementService.required(input.ownerAgentId(), "Agent ID"),
                AiAgentManagementService.required(input.policyKey(), "RAG 策略编码"),
                AiAgentManagementService.required(input.semanticVersion(), "版本号"),
                input.rewriteQueryLimit(), input.vectorTopK(), input.ftsTopK(), input.fusionTopK(),
                input.rerankTopK(), input.contextTokenLimit(), input.citationLimit(), "DRAFT",
                AiAgentManagementService.required(input.checksum(), "校验和"), USER_ID,
                current == null ? now : current.createdAt(), null,
                input.finalEvidenceTopK(), input.similarityCandidateThreshold(),
                input.similarityPairLimit(), input.adjacentGroupMaxParents());
        if (current == null) {
            repository.insertRagPolicy(value);
        } else {
            repository.updateRagPolicy(value);
        }
        return value;
    }

    @Transactional
    public ModelPolicyPO transitionModel(String id, String targetStatus) {
        ModelPolicyPO current = getModelPolicy(requiredPolicy(id).ownerAgentDefinitionId(), id);
        String target = next(current.status(), targetStatus);
        ModelPolicyPO value = new ModelPolicyPO(
                current.id(), current.ownerAgentDefinitionId(), current.policyKey(),
                current.semanticVersion(), current.provider(), current.modelName(),
                current.temperature(), current.topP(), current.maxInputTokens(),
                current.maxOutputTokens(), current.connectTimeoutMs(), current.readTimeoutMs(),
                current.maxRetries(), target, current.checksum(), current.createdBy(),
                current.createdAt(), "PUBLISHED".equals(target) ? LocalDateTime.now() : current.publishedAt());
        repository.updateModelPolicy(value);
        return value;
    }

    @Transactional
    public RagPolicyPO transitionRag(String id, String targetStatus) {
        RagPolicyPO current = repository.findRagPolicy(id);
        if (current == null) {
            throw new AiManagementException("AI_RAG_POLICY_NOT_FOUND", "RAG 策略不存在");
        }
        String target = next(current.status(), targetStatus);
        RagPolicyPO value = new RagPolicyPO(
                current.id(), current.ownerAgentDefinitionId(), current.policyKey(),
                current.semanticVersion(), current.rewriteQueryLimit(), current.vectorTopK(),
                current.ftsTopK(), current.fusionTopK(), current.rerankTopK(),
                current.contextTokenLimit(), current.citationLimit(), target, current.checksum(),
                current.createdBy(), current.createdAt(),
                "PUBLISHED".equals(target) ? LocalDateTime.now() : current.publishedAt(),
                current.finalEvidenceTopK(), current.similarityCandidateThreshold(),
                current.similarityPairLimit(), current.adjacentGroupMaxParents());
        if (!"RETIRED".equals(target)) {
            validateEvidencePolicy(value.finalEvidenceTopK(), value.similarityCandidateThreshold(),
                    value.similarityPairLimit(), value.adjacentGroupMaxParents());
        }
        repository.updateRagPolicy(value);
        return value;
    }

    private ModelPolicyPO requiredPolicy(String id) {
        ModelPolicyPO value = repository.findModelPolicy(id);
        if (value == null) {
            throw new AiManagementException("AI_MODEL_POLICY_NOT_FOUND", "模型策略不存在");
        }
        return value;
    }

    private static String next(String current, String requested) {
        String target = AiAgentManagementService.required(requested, "目标状态").toUpperCase();
        String expected = switch (current) {
            case "DRAFT" -> "VALIDATED";
            case "VALIDATED" -> "PUBLISHED";
            case "PUBLISHED" -> "RETIRED";
            default -> null;
        };
        if (!target.equals(expected)) {
            throw new AiManagementException("AI_ASSET_STATE_INVALID", "策略状态流转无效");
        }
        return target;
    }

    private static void assertOwner(String expected, String actual) {
        if (expected == null || !expected.equals(actual)) {
            throw new AiManagementException("AI_ASSET_OWNER_MISMATCH", "策略不属于该 Agent");
        }
    }

    public record ModelPolicyInput(
            String id, String ownerAgentId, String policyKey, String semanticVersion,
            String provider, String modelName, BigDecimal temperature, BigDecimal topP,
            int maxInputTokens, int maxOutputTokens, int connectTimeoutMs,
            int readTimeoutMs, int maxRetries, String checksum) { }

    public record RagPolicyInput(
            String id, String ownerAgentId, String policyKey, String semanticVersion,
            int rewriteQueryLimit, int vectorTopK, int ftsTopK, int fusionTopK,
            int rerankTopK, int contextTokenLimit, int citationLimit, String checksum,
            Integer finalEvidenceTopK, BigDecimal similarityCandidateThreshold,
            Integer similarityPairLimit, Integer adjacentGroupMaxParents) {
        public RagPolicyInput {
            finalEvidenceTopK = finalEvidenceTopK == null ? 8 : finalEvidenceTopK;
            similarityCandidateThreshold = similarityCandidateThreshold == null
                    ? new BigDecimal("0.96") : similarityCandidateThreshold;
            similarityPairLimit = similarityPairLimit == null ? 20 : similarityPairLimit;
            adjacentGroupMaxParents = adjacentGroupMaxParents == null ? 3 : adjacentGroupMaxParents;
            validateEvidencePolicy(finalEvidenceTopK, similarityCandidateThreshold,
                    similarityPairLimit, adjacentGroupMaxParents);
        }
        public RagPolicyInput(String id, String ownerAgentId, String policyKey, String semanticVersion,
                int rewriteQueryLimit, int vectorTopK, int ftsTopK, int fusionTopK,
                int rerankTopK, int contextTokenLimit, int citationLimit, String checksum) {
            this(id, ownerAgentId, policyKey, semanticVersion, rewriteQueryLimit, vectorTopK,
                    ftsTopK, fusionTopK, rerankTopK, contextTokenLimit, citationLimit, checksum,
                    null, null, null, null);
        }
    }

    static void validateEvidencePolicy(Integer finalTopK, BigDecimal threshold, Integer pairLimit, Integer groupLimit) {
        if (finalTopK == null || finalTopK < 1 || finalTopK > 20
                || threshold == null || threshold.compareTo(new BigDecimal("0.85")) < 0
                || threshold.compareTo(BigDecimal.ONE) > 0 || pairLimit == null
                || pairLimit < 1 || pairLimit > 50 || groupLimit == null || groupLimit < 1 || groupLimit > 5) {
            throw new AiManagementException("AI_RAG_POLICY_RANGE_INVALID", "证据策略超出允许范围，旧策略须创建新版本");
        }
    }
}
