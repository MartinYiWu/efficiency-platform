package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.math.BigDecimal;
import java.util.List;

/** 不可变智能客服 Release Bundle 的完整传输快照。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceReleaseRequest(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("agent_key") String agentKey,
        @JsonProperty("agent_version") String agentVersion,
        @JsonProperty("graph_key") String graphKey,
        @JsonProperty("graph_version") String graphVersion,
        @JsonProperty("environment") String environment,
        @JsonProperty("prompt_bindings") List<PromptBinding> promptBindings,
        @JsonProperty("model_policy") ModelPolicy modelPolicy,
        @JsonProperty("rag_policy") RagPolicy ragPolicy,
        @JsonProperty("knowledge_bindings") List<KnowledgeBinding> knowledgeBindings,
        @JsonProperty("tool_allowlist") List<String> toolAllowlist,
        @JsonProperty("output_contract_version") String outputContractVersion,
        @JsonProperty("safety_rule_version") String safetyRuleVersion,
        @JsonProperty("snapshot_checksum") String snapshotChecksum,
        // 旧 /1 快照缺少该字段，禁止序列化补 null 后改变其校验和。
        @JsonInclude(JsonInclude.Include.NON_NULL)
        @JsonProperty("large_context_model_policy") ModelPolicy largeContextModelPolicy) {

    public CustomerServiceReleaseRequest(String contractVersion, String agentKey, String agentVersion,
            String graphKey, String graphVersion, String environment, List<PromptBinding> promptBindings,
            ModelPolicy modelPolicy, RagPolicy ragPolicy, List<KnowledgeBinding> knowledgeBindings,
            List<String> toolAllowlist, String outputContractVersion, String safetyRuleVersion, String snapshotChecksum) {
        this(contractVersion, agentKey, agentVersion, graphKey, graphVersion, environment,
                promptBindings, modelPolicy, ragPolicy, knowledgeBindings, toolAllowlist,
                outputContractVersion, safetyRuleVersion, snapshotChecksum, null);
    }

    public CustomerServiceReleaseRequest {
        if (!"customer-service-release/1".equals(contractVersion)
                && !"customer-service-release/2".equals(contractVersion)) {
            throw new IllegalArgumentException("Release 契约版本无效");
        }
        if (!"customer-service".equals(agentKey)) {
            throw new IllegalArgumentException("agent_key 必须为 customer-service");
        }
        CustomerServiceDtoSupport.requireText(agentVersion, "agent_version");
        CustomerServiceDtoSupport.requireText(graphKey, "graph_key");
        CustomerServiceDtoSupport.requireText(graphVersion, "graph_version");
        CustomerServiceDtoSupport.requireText(environment, "environment");
        promptBindings = CustomerServiceDtoSupport.immutableList(promptBindings, "prompt_bindings");
        if (modelPolicy == null || ragPolicy == null) {
            throw new IllegalArgumentException("model_policy 和 rag_policy 不能为空");
        }
        knowledgeBindings = CustomerServiceDtoSupport.immutableList(knowledgeBindings, "knowledge_bindings");
        toolAllowlist = CustomerServiceDtoSupport.immutableList(toolAllowlist, "tool_allowlist");
        CustomerServiceDtoSupport.requireText(outputContractVersion, "output_contract_version");
        CustomerServiceDtoSupport.requireText(safetyRuleVersion, "safety_rule_version");
        CustomerServiceDtoSupport.requireText(snapshotChecksum, "snapshot_checksum");
        if (contractVersion.endsWith("/1")) {
            if (largeContextModelPolicy != null || ragPolicy.finalEvidenceTopK() != null
                    || ragPolicy.similarityCandidateThreshold() != null || ragPolicy.similarityPairLimit() != null
                    || ragPolicy.adjacentGroupMaxParents() != null) {
                throw new IllegalArgumentException("旧版 Release 不接受证据策略扩展");
            }
        } else {
            ragPolicy.validateEvidencePolicy();
            if (largeContextModelPolicy != null && largeContextModelPolicy.maxInputTokens() <= modelPolicy.maxInputTokens()) {
                throw new IllegalArgumentException("备选模型输入上限必须严格大于主模型");
            }
            for (String stage : List.of("equivalence", "conflict_screen", "evidence_extract")) {
                var bindings = promptBindings.stream().filter(value -> stage.equals(value.stageKey())).toList();
                if (bindings.size() != 1 || !bindings.getFirst().messages().stream().map(PromptMessage::role).toList()
                        .equals(List.of("SYSTEM", "USER"))) {
                    throw new IllegalArgumentException("证据阶段必须绑定独立 SYSTEM、USER 消息");
                }
            }
        }
    }

    /** 一个执行阶段绑定的确切 Prompt 版本及其有序角色消息。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record PromptBinding(
            @JsonProperty("stage_key") String stageKey,
            @JsonProperty("ordinal") int ordinal,
            @JsonProperty("prompt_key") String promptKey,
            @JsonProperty("prompt_version") String promptVersion,
            @JsonProperty("checksum") String checksum,
            @JsonProperty("messages") List<PromptMessage> messages) {
    }

    /** Prompt 的一条角色消息，正文来自数据库发布版本。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record PromptMessage(
            @JsonProperty("ordinal") int ordinal,
            @JsonProperty("role") String role,
            @JsonProperty("message_key") String messageKey,
            @JsonProperty("content_template") String contentTemplate,
            @JsonProperty("content_format") String contentFormat,
            @JsonProperty("trusted_instruction") boolean trustedInstruction,
            @JsonProperty("checksum") String checksum,
            @JsonProperty("variables") List<PromptVariable> variables) {
    }

    /** Prompt 模板变量的来源、类型和不可信内容边界。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record PromptVariable(
            @JsonProperty("variable_name") String variableName,
            @JsonProperty("value_type") String valueType,
            @JsonProperty("value_source") String valueSource,
            @JsonProperty("required") boolean required,
            @JsonProperty("sensitive") boolean sensitive,
            @JsonProperty("max_length") Integer maxLength,
            @JsonProperty("allow_untrusted_content") boolean allowUntrustedContent) {
    }

    /** 智能客服私有模型策略的冻结快照，不包含 Provider 凭据。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record ModelPolicy(
            @JsonProperty("policy_key") String policyKey,
            @JsonProperty("semantic_version") String semanticVersion,
            @JsonProperty("provider") String provider,
            @JsonProperty("model_name") String modelName,
            @JsonProperty("temperature") BigDecimal temperature,
            @JsonProperty("top_p") BigDecimal topP,
            @JsonProperty("max_input_tokens") int maxInputTokens,
            @JsonProperty("max_output_tokens") int maxOutputTokens,
            @JsonProperty("connect_timeout_ms") int connectTimeoutMs,
            @JsonProperty("read_timeout_ms") int readTimeoutMs,
            @JsonProperty("max_retries") int maxRetries,
            @JsonProperty("checksum") String checksum) {
    }

    /** 智能客服私有 RAG 策略的冻结快照；扩展字段仅 /2 必填，/1 保留缺省状态。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record RagPolicy(
            @JsonProperty("policy_key") String policyKey,
            @JsonProperty("semantic_version") String semanticVersion,
            @JsonProperty("rewrite_query_limit") int rewriteQueryLimit,
            @JsonProperty("vector_top_k") int vectorTopK,
            @JsonProperty("fts_top_k") int ftsTopK,
            @JsonProperty("fusion_top_k") int fusionTopK,
            @JsonProperty("rerank_top_k") int rerankTopK,
            @JsonProperty("context_token_limit") int contextTokenLimit,
            @JsonProperty("citation_limit") int citationLimit,
            @JsonProperty("checksum") String checksum,
            @JsonInclude(JsonInclude.Include.NON_NULL) @JsonProperty("final_evidence_top_k") Integer finalEvidenceTopK,
            @JsonInclude(JsonInclude.Include.NON_NULL) @JsonProperty("similarity_candidate_threshold") BigDecimal similarityCandidateThreshold,
            @JsonInclude(JsonInclude.Include.NON_NULL) @JsonProperty("similarity_pair_limit") Integer similarityPairLimit,
            @JsonInclude(JsonInclude.Include.NON_NULL) @JsonProperty("adjacent_group_max_parents") Integer adjacentGroupMaxParents) {
        public RagPolicy(String policyKey, String semanticVersion, int rewriteQueryLimit,
                int vectorTopK, int ftsTopK, int fusionTopK, int rerankTopK, int contextTokenLimit,
                int citationLimit, String checksum) {
            this(policyKey, semanticVersion, rewriteQueryLimit, vectorTopK, ftsTopK, fusionTopK,
                    rerankTopK, contextTokenLimit, citationLimit, checksum, null, null, null, null);
        }
        public void validateEvidencePolicy() {
            if (finalEvidenceTopK == null || finalEvidenceTopK < 1 || finalEvidenceTopK > 20
                    || similarityCandidateThreshold == null || similarityCandidateThreshold.compareTo(new BigDecimal("0.85")) < 0
                    || similarityCandidateThreshold.compareTo(BigDecimal.ONE) > 0 || similarityPairLimit == null
                    || similarityPairLimit < 1 || similarityPairLimit > 50 || adjacentGroupMaxParents == null
                    || adjacentGroupMaxParents < 1 || adjacentGroupMaxParents > 5) {
                throw new IllegalArgumentException("证据策略超出允许范围");
            }
        }
    }

    /** Release 可检索的知识库与确切索引版本。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record KnowledgeBinding(
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("priority") int priority,
            @JsonProperty("required") boolean required) {
    }
}
