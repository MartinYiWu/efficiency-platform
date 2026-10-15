package com.aiep.aihub.repository.operation;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("ai_operation_message")
public class OperationMessagePO {
    @TableId
    private String id;
    private String conversationId;
    private String tenantId;
    private String role;
    private String content;
    private String runId;
    private String clientRequestId;
    private LocalDateTime createdAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public String getClientRequestId() { return clientRequestId; }
    public void setClientRequestId(String clientRequestId) { this.clientRequestId = clientRequestId; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
