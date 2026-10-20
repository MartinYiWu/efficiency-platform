package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Java 向独立智能客服 Agent 提交的一次运行请求。
 * 历史只包含最近十二条已完成消息，总字符数不得超过 12000。
 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceRunRequest(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("request_id") String requestId,
        @JsonProperty("conversation_id") String conversationId,
        @JsonProperty("tenant_id") String tenantId,
        @JsonProperty("user_id") String userId,
        @JsonProperty("agent_release_id") String agentReleaseId,
        @JsonProperty("message") String message,
        @JsonProperty("history") List<HistoryMessage> history) {

    public CustomerServiceRunRequest {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-run/1");
        CustomerServiceDtoSupport.requireText(requestId, "request_id");
        CustomerServiceDtoSupport.requireText(conversationId, "conversation_id");
        CustomerServiceDtoSupport.requireText(tenantId, "tenant_id");
        CustomerServiceDtoSupport.requireText(userId, "user_id");
        CustomerServiceDtoSupport.requireText(agentReleaseId, "agent_release_id");
        CustomerServiceDtoSupport.requireText(message, "message");
        history = CustomerServiceDtoSupport.immutableList(history, "history");
        if (history.size() > 12) {
            throw new IllegalArgumentException("history 最多包含 12 条消息");
        }
        int totalCharacters = history.stream().mapToInt(item -> item.content().length()).sum();
        if (totalCharacters > 12000) {
            throw new IllegalArgumentException("history 总字符数不得超过 12000");
        }
    }

    /** 有界历史中的一条已完成消息，只允许 user 或 assistant 角色。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record HistoryMessage(
            @JsonProperty("role") String role,
            @JsonProperty("content") String content) {
        public HistoryMessage {
            if (!"user".equals(role) && !"assistant".equals(role)) {
                throw new IllegalArgumentException("history.role 只允许 user 或 assistant");
            }
            CustomerServiceDtoSupport.requireText(content, "history.content");
        }
    }
}
