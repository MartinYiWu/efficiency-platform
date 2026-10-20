package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** Agent 接收、取消或查询运行后返回的强类型状态。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceRunView(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("run_id") String runId,
        @JsonProperty("request_id") String requestId,
        @JsonProperty("status") Status status) {

    public CustomerServiceRunView {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-run-view/1");
        CustomerServiceDtoSupport.requireText(runId, "run_id");
        CustomerServiceDtoSupport.requireText(requestId, "request_id");
        if (status == null) {
            throw new IllegalArgumentException("status 不能为空");
        }
    }

    /** Agent 运行终态和非终态全集。 */
    public enum Status {
        PENDING,
        RUNNING,
        SUCCEEDED,
        FAILED,
        TIMED_OUT,
        CANCELLED
    }
}
