package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 文档摄取任务请求；Agent 下载后必须复核大小与 SHA-256。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceIngestRequest(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("task_id") String taskId,
        @JsonProperty("tenant_id") String tenantId,
        @JsonProperty("knowledge_base_id") String knowledgeBaseId,
        @JsonProperty("document_id") String documentId,
        @JsonProperty("document_version_id") String documentVersionId,
        @JsonProperty("document_title") String documentTitle,
        @JsonProperty("version_no") int versionNo,
        @JsonProperty("file_name") String fileName,
        @JsonProperty("content_type") String contentType,
        @JsonProperty("size_bytes") long sizeBytes,
        @JsonProperty("sha256") String sha256,
        @JsonProperty("download_url") String downloadUrl) {
    public CustomerServiceIngestRequest {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-ingest/1");
        CustomerServiceDtoSupport.requireText(taskId, "task_id");
        CustomerServiceDtoSupport.requireText(tenantId, "tenant_id");
        CustomerServiceDtoSupport.requireText(knowledgeBaseId, "knowledge_base_id");
        CustomerServiceDtoSupport.requireText(documentId, "document_id");
        CustomerServiceDtoSupport.requireText(documentVersionId, "document_version_id");
        CustomerServiceDtoSupport.requireText(documentTitle, "document_title");
        if (versionNo < 1) {
            throw new IllegalArgumentException("version_no 必须为正整数");
        }
        CustomerServiceDtoSupport.requireText(fileName, "file_name");
        CustomerServiceDtoSupport.requireText(contentType, "content_type");
        if (sizeBytes < 1 || sizeBytes > 10L * 1024 * 1024) {
            throw new IllegalArgumentException("size_bytes 必须在 1 到 10 MiB 之间");
        }
        CustomerServiceDtoSupport.requireText(sha256, "sha256");
        CustomerServiceDtoSupport.requireText(downloadUrl, "download_url");
    }
}
