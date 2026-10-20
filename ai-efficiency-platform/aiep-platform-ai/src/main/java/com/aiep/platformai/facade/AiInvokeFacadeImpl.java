package com.aiep.platformai.facade;

import com.aiep.platformai.agent.AgentClient;
import com.aiep.platformai.agent.CustomerServiceAgentClient;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class AiInvokeFacadeImpl implements AiInvokeFacade {
    private final AgentClient agentClient;
    private final CustomerServiceAgentClient customerServiceAgentClient;

    public AiInvokeFacadeImpl(AgentClient agentClient, CustomerServiceAgentClient customerServiceAgentClient) {
        this.agentClient = agentClient;
        this.customerServiceAgentClient = customerServiceAgentClient;
    }

    @Override public AiTextResponse generateText(AiTextRequest request) { return agentClient.generateText(request); }
    @Override public void streamChat(AiStreamRequest request, AiStreamObserver observer) { agentClient.streamChat(request, observer); }
    @Override public AiTextResponse executeSkill(AiSkillExecuteRequest request) { return agentClient.executeSkill(request); }
    @Override public void streamKbQa(AiKbQaRequest request, AiStreamObserver observer) { agentClient.streamKbQa(request, observer); }
    @Override public AiTaskStatusResponse submitIngest(AiIngestRequest request) { return agentClient.submitIngest(request); }
    @Override public AiTaskStatusResponse queryTask(String taskId) { return agentClient.queryTask(taskId); }
    @Override public void deleteVectors(AiVectorDeleteRequest request) { agentClient.deleteVectors(request); }
    @Override public OperationAgentRunResponse submitOperationMessage(String conversationId, OperationAgentMessageRequest request) { return agentClient.submitOperationMessage(conversationId, request); }
    @Override public Flux<OperationAgentRunEvent> streamOperationRunEvents(String runId, String tenantId, long afterSequence) { return agentClient.streamOperationRunEvents(runId, tenantId, afterSequence); }
    @Override public OperationAgentCancelResponse cancelOperationRun(String runId, String tenantId) { return agentClient.cancelOperationRun(runId, tenantId); }
    @Override public CustomerServiceReleaseAck publishCustomerServiceRelease(String releaseId, CustomerServiceReleaseRequest request) { return customerServiceAgentClient.publishRelease(releaseId, request); }
    @Override public CustomerServiceIngestView submitCustomerServiceIngest(CustomerServiceIngestRequest request) { return customerServiceAgentClient.submitIngest(request); }
    @Override public CustomerServiceIngestView queryCustomerServiceIngest(String taskId) { return customerServiceAgentClient.getIngest(taskId); }
    @Override public CustomerServiceIndexVerifyView verifyCustomerServiceIndex(String releaseId) { return customerServiceAgentClient.verifyIndex(releaseId); }
    @Override public CustomerServiceRunView submitCustomerServiceMessage(String conversationId, CustomerServiceRunRequest request) { return customerServiceAgentClient.submitMessage(conversationId, request); }
    @Override public Flux<CustomerServiceRunEvent> streamCustomerServiceRunEvents(String runId, long afterSequence) { return customerServiceAgentClient.streamRun(runId, afterSequence); }
    @Override public CustomerServiceRunView cancelCustomerServiceRun(String runId) { return customerServiceAgentClient.cancelRun(runId); }
    @Override public CustomerServiceDebugView debugCustomerServiceRag(CustomerServiceDebugRequest request) { return customerServiceAgentClient.runDebug(request); }
}
