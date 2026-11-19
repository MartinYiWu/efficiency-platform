package com.aiep.platformai.agent;

import com.aiep.platformai.api.dto.AiIngestRequest;
import com.aiep.platformai.api.dto.AiKbQaRequest;
import com.aiep.platformai.api.dto.AiSkillExecuteRequest;
import com.aiep.platformai.api.dto.AiStreamObserver;
import com.aiep.platformai.api.dto.AiStreamRequest;
import com.aiep.platformai.api.dto.AiTaskStatusResponse;
import com.aiep.platformai.api.dto.AiTextRequest;
import com.aiep.platformai.api.dto.AiTextResponse;
import com.aiep.platformai.api.dto.AiVectorDeleteRequest;
import com.aiep.platformai.api.dto.OperationAgentCancelResponse;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformai.api.dto.OperationAgentRunResponse;
import reactor.core.publisher.Flux;

/** Internal transport seam. Its HTTP implementation is intentionally deferred. */
public interface AgentClient {
    default com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt upsertMemoryIndex(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Upsert request){throw new UnsupportedOperationException("MEMORY_INDEX_TRANSPORT_REQUIRED");}
    default com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt deleteMemoryIndex(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Delete request){throw new UnsupportedOperationException("MEMORY_INDEX_TRANSPORT_REQUIRED");}
    default com.aiep.platformai.api.dto.MemorySemanticTransport.RecallResult recallMemory(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Recall request){throw new UnsupportedOperationException("MEMORY_RECALL_TRANSPORT_REQUIRED");}
    default com.aiep.platformai.api.dto.MemoryDeriveRequest queryMemoryDerivePlan(String tenantId,String executionId) {
        throw new UnsupportedOperationException("MEMORY_DERIVE_TRANSPORT_REQUIRED");
    }
    default void finishMemoryDerive(String tenantId,String executionId,String planId,String planFingerprint,String status) {
        throw new UnsupportedOperationException("MEMORY_DERIVE_TRANSPORT_REQUIRED");
    }
    default com.aiep.platformai.api.dto.MemoryDeriveResponse deriveMemory(String tenantId, com.aiep.platformai.api.dto.MemoryDeriveRequest request) {
        throw new UnsupportedOperationException("MEMORY_DERIVE_TRANSPORT_REQUIRED");
    }
    /** 只读取Agent持久READY wait，不创建等待或新任务。 */
    default com.aiep.platformai.api.dto.MemoryContextWait queryMemoryWait(String tenantId,String executionId) {
        throw new UnsupportedOperationException("MEMORY_WAIT_TRANSPORT_REQUIRED");
    }
    /** 按原事件精确读取历史wait，供同候选重传；不会创建新等待。 */
    default com.aiep.platformai.api.dto.MemoryContextWait queryMemoryWait(String tenantId,String executionId,String eventRef) {
        throw new UnsupportedOperationException("MEMORY_WAIT_TRANSPORT_REQUIRED");
    }
    default com.aiep.platformai.api.dto.MemoryResumeReceipt resumeMemoryExecution(String tenantId,String executionId,com.aiep.platformai.api.dto.MemoryResumeRequest request) {
        throw new UnsupportedOperationException("MEMORY_RESUME_TRANSPORT_REQUIRED");
    }
    default com.aiep.platformai.api.dto.MemoryCleanupReceipt cleanupMemoryExecution(String tenantId,String executionId,com.aiep.platformai.api.dto.MemoryCleanupRequest request) {
        throw new UnsupportedOperationException("MEMORY_CLEANUP_TRANSPORT_REQUIRED");
    }
    default com.aiep.platformai.api.dto.MemoryRuntimeManifest queryMemoryManifest(String tenantId,String executionId) {
        throw new UnsupportedOperationException("MEMORY_MANIFEST_TRANSPORT_REQUIRED");
    }
    AiTextResponse generateText(AiTextRequest request);
    void streamChat(AiStreamRequest request, AiStreamObserver observer);
    AiTextResponse executeSkill(AiSkillExecuteRequest request);
    void streamKbQa(AiKbQaRequest request, AiStreamObserver observer);
    AiTaskStatusResponse submitIngest(AiIngestRequest request);
    AiTaskStatusResponse queryTask(String taskId);
    void deleteVectors(AiVectorDeleteRequest request);
    OperationAgentRunResponse submitOperationMessage(String conversationId, OperationAgentMessageRequest request);
    Flux<OperationAgentRunEvent> streamOperationRunEvents(String runId, String tenantId, long afterSequence);
    OperationAgentCancelResponse cancelOperationRun(String runId, String tenantId);
}
