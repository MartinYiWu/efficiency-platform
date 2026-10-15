package com.aiep.aihub.repository.operation;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("ai_operation_artifact")
public class OperationArtifactPO {
    @TableId
    private String id;
    private String conversationId;
    private String runId;
    private String sourceResearchRunId;
    private String tenantId;
    private String artifactType;
    private String platform;
    private int versionNo;
    private String title;
    private String bodyMarkdown;
    private String bodyHtml;
    private String internalMetadata;
    private LocalDateTime createdAt;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getConversationId() { return conversationId; }
    public void setConversationId(String conversationId) { this.conversationId = conversationId; }
    public String getRunId() { return runId; }
    public void setRunId(String runId) { this.runId = runId; }
    public String getSourceResearchRunId() { return sourceResearchRunId; }
    public void setSourceResearchRunId(String sourceResearchRunId) { this.sourceResearchRunId = sourceResearchRunId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getArtifactType() { return artifactType; }
    public void setArtifactType(String artifactType) { this.artifactType = artifactType; }
    public String getPlatform() { return platform; }
    public void setPlatform(String platform) { this.platform = platform; }
    public int getVersionNo() { return versionNo; }
    public void setVersionNo(int versionNo) { this.versionNo = versionNo; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getBodyMarkdown() { return bodyMarkdown; }
    public void setBodyMarkdown(String bodyMarkdown) { this.bodyMarkdown = bodyMarkdown; }
    public String getBodyHtml() { return bodyHtml; }
    public void setBodyHtml(String bodyHtml) { this.bodyHtml = bodyHtml; }
    public String getInternalMetadata() { return internalMetadata; }
    public void setInternalMetadata(String internalMetadata) { this.internalMetadata = internalMetadata; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
