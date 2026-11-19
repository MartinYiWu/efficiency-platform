package com.aiep.platformai.facade;

import com.aiep.platformai.agent.AgentClient;
import com.aiep.platformai.agent.CustomerServiceAgentClient;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.AiInvocationException;
import com.aiep.platformai.api.dto.*;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class AiInvokeFacadeImpl implements AiInvokeFacade {
    @Override public MemorySemanticTransport.Receipt upsertMemoryIndex(String tenantId,MemorySemanticTransport.Upsert request){try{return agentClient.upsertMemoryIndex(tenantId,request);}catch(com.aiep.platformai.agent.AgentTransportException error){throw new AiInvocationException(error.getStatusCode(),error.getErrorCode(),"记忆索引暂不可用");}}
    @Override public MemorySemanticTransport.Receipt deleteMemoryIndex(String tenantId,MemorySemanticTransport.Delete request){try{return agentClient.deleteMemoryIndex(tenantId,request);}catch(com.aiep.platformai.agent.AgentTransportException error){throw new AiInvocationException(error.getStatusCode(),error.getErrorCode(),"记忆索引清理暂不可用");}}
    @Override public MemorySemanticTransport.RecallResult recallMemory(String tenantId,MemorySemanticTransport.Recall request){try{return agentClient.recallMemory(tenantId,request);}catch(com.aiep.platformai.agent.AgentTransportException error){throw new AiInvocationException(error.getStatusCode(),error.getErrorCode(),"记忆召回暂不可用");}}
    @Override public MemoryDeriveRequest queryMemoryDerivePlan(String tenantId,String executionId) {
        try { return agentClient.queryMemoryDerivePlan(tenantId,executionId); }
        catch(com.aiep.platformai.agent.AgentTransportException error) {
            throw new com.aiep.platformai.api.AiInvocationException(error.getStatusCode(),error.getErrorCode(),"摘要计划读取未完成");
        }
    }
    @Override public void finishMemoryDerive(String tenantId,String executionId,String planId,String planFingerprint,String status) {
        try { agentClient.finishMemoryDerive(tenantId,executionId,planId,planFingerprint,status); }
        catch(com.aiep.platformai.agent.AgentTransportException error) {
            throw new com.aiep.platformai.api.AiInvocationException(error.getStatusCode(),error.getErrorCode(),"摘要等待处理未完成");
        }
    }
    @Override public MemoryDeriveResponse deriveMemory(String tenantId,MemoryDeriveRequest request) {
        try { return agentClient.deriveMemory(tenantId,request); }
        catch(com.aiep.platformai.agent.AgentTransportException error) {
            throw new com.aiep.platformai.api.AiInvocationException(error.getStatusCode(),error.getErrorCode(),"摘要处理未完成");
        }
    }
    @Override public MemoryContextWait queryMemoryWait(String tenantId,String executionId) {
        return agentClient.queryMemoryWait(tenantId,executionId);
    }
    @Override public MemoryContextWait queryMemoryWait(String tenantId,String executionId,String eventRef) {
        return agentClient.queryMemoryWait(tenantId,executionId,eventRef);
    }
    @Override public MemoryResumeReceipt resumeMemoryExecution(String tenantId,String executionId,MemoryResumeRequest request) {
        return agentClient.resumeMemoryExecution(tenantId,executionId,request);
    }
    @Override public MemoryCleanupReceipt cleanupMemoryExecution(String tenantId,String executionId,MemoryCleanupRequest request) {
        return agentClient.cleanupMemoryExecution(tenantId,executionId,request);
    }
    @Override public MemoryRuntimeManifest queryMemoryManifest(String tenantId,String executionId) {
        return agentClient.queryMemoryManifest(tenantId,executionId);
    }
    private final AgentClient agentClient;
    private final CustomerServiceAgentClient customerServiceAgentClient;

    public AiInvokeFacadeImpl(AgentClient agentClient, CustomerServiceAgentClient customerServiceAgentClient) {
        this.agentClient = agentClient;
        this.customerServiceAgentClient = customerServiceAgentClient;
    }

    @Override public AiTextResponse generateText(AiTextRequest request) { return agentClient.generateText(request); }
    @Override public void streamChat(AiStreamRequest request, AiStreamObserver observer) { agentClient.streamChat(request, observer); }
    @Override public AiTextResponse executeSkill(AiSkillExecuteRequest request) {
        try { return agentClient.executeSkill(request); }
        catch (com.aiep.platformai.agent.AgentTransportException error) {
            throw new com.aiep.platformai.api.AiInvocationException(error.getStatusCode(),error.getErrorCode(),"AI任务未完成，请核对配置、预算及运行状态");
        }
    }
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
    @Override public CustomerServiceIndexVerifyView verifyCustomerServiceIndex(CustomerServiceIndexVerifyRequest request) { return customerServiceAgentClient.verifyIndex(request); }
    @Override public CustomerServiceRunView submitCustomerServiceMessage(String conversationId, CustomerServiceRunRequest request) { return customerServiceAgentClient.submitMessage(conversationId, request); }
    @Override public Flux<CustomerServiceRunEvent> streamCustomerServiceRunEvents(String runId, long afterSequence) { return customerServiceAgentClient.streamRun(runId, afterSequence); }
    @Override public CustomerServiceRunView cancelCustomerServiceRun(String runId) { return customerServiceAgentClient.cancelRun(runId); }
    @Override public CustomerServiceDebugView debugCustomerServiceRag(CustomerServiceDebugRequest request) { return customerServiceAgentClient.runDebug(request); }
}
