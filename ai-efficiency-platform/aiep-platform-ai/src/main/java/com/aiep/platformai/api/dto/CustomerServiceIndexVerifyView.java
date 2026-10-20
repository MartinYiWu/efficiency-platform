package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 候选索引在 Agent 侧的结构与内容完整性验证结果。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceIndexVerifyView(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("release_id") String releaseId,
        @JsonProperty("status") String status,
        @JsonProperty("document_count") int documentCount,
        @JsonProperty("chunk_count") int chunkCount,
        @JsonProperty("checksum") String checksum,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("error_message") String errorMessage) {
}
