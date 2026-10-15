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
