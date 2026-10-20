package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** RAG 调试的阶段化结果，不包含隐藏思维链或完整 Prompt。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceDebugView(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("debug_run_id") String debugRunId,
        @JsonProperty("status") String status,
        @JsonProperty("stages") List<Stage> stages,
        @JsonProperty("answer_mode") String answerMode,
        @JsonProperty("answer_markdown") String answerMarkdown,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("error_message") String errorMessage) {

    /** 一项可回放的结构化调试阶段。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Stage(
            @JsonProperty("stage_key") String stageKey,
            @JsonProperty("status") String status,
            @JsonProperty("public_summary") String publicSummary,
            @JsonProperty("evidence") List<Evidence> evidence) {
    }

    /** 调试阶段返回的受控证据摘要。 */
    @JsonIgnoreProperties(ignoreUnknown = false)
    public record Evidence(
            @JsonProperty("chunk_id") String chunkId,
            @JsonProperty("document_version_id") String documentVersionId,
            @JsonProperty("section_path") String sectionPath,
            @JsonProperty("score") double score,
            @JsonProperty("excerpt") String excerpt) {
    }
}
