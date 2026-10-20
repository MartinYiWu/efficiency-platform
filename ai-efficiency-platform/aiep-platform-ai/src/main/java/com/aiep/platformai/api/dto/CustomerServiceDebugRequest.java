package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 不写入员工会话的 RAG 调试请求。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceDebugRequest(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("agent_key") String agentKey,
        @JsonProperty("tenant_id") String tenantId,
        @JsonProperty("question") String question,
        @JsonProperty("agent_release_id") String agentReleaseId,
        @JsonProperty("agent_version_id") String agentVersionId,
        @JsonProperty("rag_policy_version_id") String ragPolicyVersionId,
        @JsonProperty("knowledge_bindings") List<KnowledgeBinding> knowledgeBindings) {

    public CustomerServiceDebugRequest {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-rag-debug/1");
        if (!"customer-service".equals(agentKey)) {
            throw new IllegalArgumentException("agent_key 必须为 customer-service");
        }
        CustomerServiceDtoSupport.requireText(tenantId, "tenant_id");
        CustomerServiceDtoSupport.requireText(question, "question");
        CustomerServiceDtoSupport.requireText(agentReleaseId, "agent_release_id");
        CustomerServiceDtoSupport.requireText(agentVersionId, "agent_version_id");
        CustomerServiceDtoSupport.requireText(ragPolicyVersionId, "rag_policy_version_id");
        knowledgeBindings = CustomerServiceDtoSupport.immutableList(knowledgeBindings, "knowledge_bindings");
    }

    /** 调试限定的知识库与确切索引版本。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record KnowledgeBinding(
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("index_release_id") String indexReleaseId) {
    }
}
