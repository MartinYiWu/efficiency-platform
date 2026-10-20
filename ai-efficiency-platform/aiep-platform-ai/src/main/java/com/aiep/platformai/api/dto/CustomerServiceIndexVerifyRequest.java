package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** 候选索引验证请求；成员快照来自 Java 业务真相库。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceIndexVerifyRequest(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("release_id") String releaseId,
        @JsonProperty("knowledge_base_id") String knowledgeBaseId,
        @JsonProperty("documents") List<DocumentMember> documents) {
    public CustomerServiceIndexVerifyRequest {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-index-verify/1");
        CustomerServiceDtoSupport.requireText(releaseId, "release_id");
        CustomerServiceDtoSupport.requireText(knowledgeBaseId, "knowledge_base_id");
        if (documents == null || documents.isEmpty()) {
            throw new IllegalArgumentException("documents 不能为空");
        }
        documents = List.copyOf(documents);
    }

    @JsonIgnoreProperties(ignoreUnknown = false)
    public record DocumentMember(
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("document_sha256") String documentSha256) {
        public DocumentMember {
            CustomerServiceDtoSupport.requireText(documentId, "document_id");
            CustomerServiceDtoSupport.requireText(documentVersionId, "document_version_id");
            if (documentSha256 == null || !documentSha256.matches("[a-f0-9]{64}")) {
                throw new IllegalArgumentException("document_sha256 无效");
            }
        }
    }
}
