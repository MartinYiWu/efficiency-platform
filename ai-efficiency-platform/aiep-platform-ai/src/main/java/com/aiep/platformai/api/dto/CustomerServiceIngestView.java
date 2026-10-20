package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 文档摄取任务的阶段、进度和安全错误摘要。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceIngestView(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("task_id") String taskId,
        @JsonProperty("status") String status,
        @JsonProperty("stage") String stage,
        @JsonProperty("progress_percent") int progressPercent,
        @JsonProperty("error_code") String errorCode,
        @JsonProperty("error_message") String errorMessage) {
    public CustomerServiceIngestView {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-ingest-view/1");
        CustomerServiceDtoSupport.requireText(taskId, "task_id");
        CustomerServiceDtoSupport.requireText(status, "status");
        CustomerServiceDtoSupport.requireText(stage, "stage");
        CustomerServiceDtoSupport.requireRange(progressPercent, 0, 100, "progress_percent");
    }
}
