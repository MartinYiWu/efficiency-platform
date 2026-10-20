package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

/** Agent SSE 中单调递增的一条智能客服运行事件。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceRunEvent(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("run_id") String runId,
        @JsonProperty("sequence") long sequence,
        @JsonProperty("event_type") String eventType,
        @JsonProperty("status") CustomerServiceRunView.Status status,
        @JsonProperty("occurred_at") Instant occurredAt,
        @JsonProperty("payload") Payload payload) {

    public CustomerServiceRunEvent {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-run-event/1");
        CustomerServiceDtoSupport.requireText(runId, "run_id");
        if (sequence < 1) {
            throw new IllegalArgumentException("sequence 必须大于 0");
        }
        CustomerServiceDtoSupport.requireText(eventType, "event_type");
        if (status == null || occurredAt == null || payload == null) {
            throw new IllegalArgumentException("status、occurred_at 和 payload 不能为空");
        }
    }

    /**
     * 公开传输载荷。不同事件只填写与该事件相关的字段；候选内容与 Prompt 不进入公开 SSE。
     */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Payload(
            @JsonProperty("stage") String stage,
            @JsonProperty("progress_percent") Integer progressPercent,
            @JsonProperty("public_summary") String publicSummary,
            @JsonProperty("delta") String delta,
            @JsonProperty("answer_mode") String answerMode,
            @JsonProperty("citation") Citation citation,
            @JsonProperty("error_code") String errorCode,
            @JsonProperty("error_message") String errorMessage) {
    }

    /** 回答完成时由 Agent 返回、随后由 Java 冻结的引用事实。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Citation(
            @JsonProperty("citation_no") int citationNo,
            @JsonProperty("knowledge_base_id") String knowledgeBaseId,
            @JsonProperty("document_id") String documentId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("index_release_id") String indexReleaseId,
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("document_title") String documentTitle,
            @JsonProperty("version_no") int versionNo,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("page_no") Integer pageNo,
            @JsonProperty("quoted_text") String quotedText,
            @JsonProperty("content_hash") String contentHash) {
    }
}
