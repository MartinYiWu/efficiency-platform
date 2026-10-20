package com.aiep.platformai.api.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

/** Agent 校验并幂等保存 Release Bundle 后返回的确认。 */
@JsonIgnoreProperties(ignoreUnknown = false)
public record CustomerServiceReleaseAck(
        @JsonProperty("contract_version") String contractVersion,
        @JsonProperty("release_id") String releaseId,
        @JsonProperty("checksum") String checksum,
        @JsonProperty("status") String status) {
    public CustomerServiceReleaseAck {
        CustomerServiceDtoSupport.requireContract(contractVersion, "customer-service-release-ack/1");
        CustomerServiceDtoSupport.requireText(releaseId, "release_id");
        CustomerServiceDtoSupport.requireText(checksum, "checksum");
        if (!"ACKNOWLEDGED".equals(status)) {
            throw new IllegalArgumentException("status 必须为 ACKNOWLEDGED");
        }
    }
}
