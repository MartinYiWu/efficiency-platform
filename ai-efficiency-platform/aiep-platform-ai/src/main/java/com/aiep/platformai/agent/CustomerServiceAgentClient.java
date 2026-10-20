package com.aiep.platformai.agent;

import com.aiep.platformai.api.dto.CustomerServiceDebugRequest;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyView;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyRequest;
import com.aiep.platformai.api.dto.CustomerServiceIngestRequest;
import com.aiep.platformai.api.dto.CustomerServiceIngestView;
import com.aiep.platformai.api.dto.CustomerServiceReleaseAck;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunView;
import reactor.core.publisher.Flux;

/** 智能客服专用内部传输缝，业务模块不得直接依赖。 */
public interface CustomerServiceAgentClient {
    CustomerServiceReleaseAck publishRelease(String releaseId, CustomerServiceReleaseRequest request);

    CustomerServiceIngestView submitIngest(CustomerServiceIngestRequest request);

    CustomerServiceIngestView getIngest(String taskId);

    CustomerServiceIndexVerifyView verifyIndex(CustomerServiceIndexVerifyRequest request);

    CustomerServiceRunView submitMessage(String conversationId, CustomerServiceRunRequest request);

    Flux<CustomerServiceRunEvent> streamRun(String runId, long afterSequence);

    CustomerServiceRunView cancelRun(String runId);

    CustomerServiceDebugView runDebug(CustomerServiceDebugRequest request);
}
