package com.aiep.aihub.repository.operation;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("ai_operation_run")
public class OperationRunPO {
    @TableId
    private String id;
    private String conversationId;
    private String tenantId;
    private String userMessageId;
    private String agentRunId;
    private String status;
    private long lastEventSequence;
    private String failureCode;
    private String failureMessage;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getUserMessageId() { return userMessageId; }
    public void setUserMessageId(String userMessageId) { this.userMessageId = userMessageId; }
    public String getAgentRunId() { return agentRunId; }
    public void setAgentRunId(String agentRunId) { this.agentRunId = agentRunId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public long getLastEventSequence() { return lastEventSequence; }
    public void setLastEventSequence(long lastEventSequence) { this.lastEventSequence = lastEventSequence; }
    public String getFailureCode() { return failureCode; }
    public void setFailureCode(String failureCode) { this.failureCode = failureCode; }
    public String getFailureMessage() { return failureMessage; }
    public void setFailureMessage(String failureMessage) { this.failureMessage = failureMessage; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
