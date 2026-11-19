package com.aiep.aihub.application.customer;

import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerServiceEventProjector {
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.aihub.application.memory.MemoryAgentPolicyService memoryAgentPolicies;
    private final CustomerServiceMappers repository;
    private final ObjectMapper objectMapper;
    private final com.aiep.aihub.application.memory.MemoryActorProvider actors;
    private final com.aiep.aihub.application.memory.MemoryContextResumeService memoryResumes;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.aihub.application.memory.MemoryPacketService memoryPackets;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.aihub.application.memory.MemoryDependencyService memoryDependencies;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.platformai.api.AiInvokeFacade ai;
    @org.springframework.beans.factory.annotation.Autowired(required=false)
    private com.aiep.aihub.application.memory.MemoryDerivePlanService memoryDerives;

    public CustomerServiceEventProjector(CustomerServiceMappers repository,ObjectMapper objectMapper) {
        this(repository,objectMapper,null,null);
    }
    @org.springframework.beans.factory.annotation.Autowired
    public CustomerServiceEventProjector(CustomerServiceMappers repository,ObjectMapper objectMapper,
            @org.springframework.lang.Nullable com.aiep.aihub.application.memory.MemoryActorProvider actors,
            @org.springframework.lang.Nullable com.aiep.aihub.application.memory.MemoryContextResumeService memoryResumes) {
        this.repository=repository;this.objectMapper=objectMapper;this.actors=actors;this.memoryResumes=memoryResumes;
    }

    @Transactional
    public PublicEvent project(String javaRunId, String tenantId, CustomerServiceRunEvent event) {
        RunPO run = repository.findRun(javaRunId, tenantId);
        if (run == null || !event.runId().equals(run.agentRunId())) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_AGENT_RUN_MISMATCH");
        }
        if("context_refresh_required".equals(event.eventType())) {
            memoryWaitReference(event);
            if(event.sequence()>run.lastEventSequence()&&!com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))
                repository.advanceRun(javaRunId,event.sequence()-1,event.sequence(),run.status(),run.answerMode(),run.failureCode(),run.failureMessage());
            // 只推进内部游标，不写员工步骤或消息；重连从客户端公开游标重新取得原wait。
            return null;
        }
        if("memory_derive_required".equals(event.eventType())) {
            memoryDeriveReferences(event);
            if(event.sequence()>run.lastEventSequence()&&!com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))repository.advanceRun(javaRunId,event.sequence()-1,event.sequence(),run.status(),run.answerMode(),run.failureCode(),run.failureMessage());
            return null;
        }
        com.aiep.aihub.api.memory.MemoryScopeDTO memoryScope=null;
        java.util.List<com.aiep.platformai.api.dto.MemoryContextPacket.Dependency> actualMemoryInputs=java.util.List.of();
        if(memoryPackets!=null&&memoryPackets.enabled()
                &&(memoryAgentPolicies==null||memoryAgentPolicies.privateMemoryDomain(tenantId,"customer-service")||memoryPackets.hasIssuedExecution(tenantId,javaRunId))
                &&java.util.Set.of("answer.delta","answer.completed","citation.ready").contains(event.eventType())) {
            memoryScope=memoryPackets.issuedScope(tenantId,javaRunId);
            memoryPackets.validateKnowledgePublication(memoryScope,javaRunId);
            actualMemoryInputs=memoryPackets.verifyManifest(memoryScope,javaRunId,run.agentRunId(),ai.queryMemoryManifest(tenantId,javaRunId));
        }
        if (event.sequence() <= run.lastEventSequence()) {
            return publicEvent(javaRunId, event, false);
        }
        String status = event.status().name();
        if (!repository.advanceRun(javaRunId, event.sequence() - 1, event.sequence(), status,
                event.payload().answerMode(), event.payload().errorCode(), event.payload().errorMessage())) {
            return null;
        }
        repository.insertRunStep(new RunStepPO(UUID.randomUUID().toString(), javaRunId, event.sequence(),
                event.payload().stage() == null ? event.eventType() : event.payload().stage(), status,
                event.payload().publicSummary(), eventJson(event), event.occurredAt(), Instant.now()));
        if ("conversation.title".equals(event.eventType())) {
            CustomerServiceConversationTitles.assignAutomatic(repository, run, event.payload().conversationTitle());
            return publicEvent(javaRunId, event, true);
        }
        MessagePO assistant = repository.findAssistantMessageByRun(javaRunId, tenantId);
        if (assistant == null) throw new IllegalStateException("CUSTOMER_SERVICE_ASSISTANT_MESSAGE_MISSING");
        if(memoryScope!=null)memoryDependencies.record(memoryScope,"MESSAGE",assistant.id(),"1",javaRunId,
            actualMemoryInputs,java.util.List.of(actualMemoryInputs),java.util.List.of());
        if ("answer.delta".equals(event.eventType())) {
            String delta = event.payload().delta() == null ? "" : event.payload().delta();
            String separator = assistant.content().isBlank() ? "" : "\n\n";
            repository.completeAssistantMessage(assistant.id(), assistant.content() + separator + delta,
                    event.payload().answerMode(), "STREAMING");
            return publicEvent(javaRunId, event, true);
        }
        if ("citation.ready".equals(event.eventType()) && event.payload().citation() != null) {
            CustomerServiceRunEvent.Citation c = event.payload().citation();
            CitationPO citation = new CitationPO(UUID.randomUUID().toString(), javaRunId, assistant.id(), c.citationNo(),
                    c.knowledgeBaseId(), c.documentId(), c.documentVersionId(), c.indexReleaseId(), c.chunkId(),
                    c.documentTitle(), c.versionNo(), c.sectionPath(), c.pageNo(), c.quotedText(), c.contentHash(), Instant.now(),
                    c.parentId(), c.citationType(), c.originalSpans());
            repository.insertCitation(citation);
            return new PublicEvent(event.sequence(), "citation.ready", citation);
        }
        if ("answer.completed".equals(event.eventType())) {
            repository.completeAssistantMessage(assistant.id(), assistant.content(), event.payload().answerMode(), "COMPLETED");
            return publicEvent(javaRunId, event, true);
        }
        if ("run.failed".equals(event.eventType())) {
            repository.completeAssistantMessage(assistant.id(), assistant.content(), null, "FAILED");
            return publicEvent(javaRunId, event, true);
        }
        if ("run.cancelled".equals(event.eventType())) {
            repository.completeAssistantMessage(assistant.id(), assistant.content(), null, "CANCELLED");
            return publicEvent(javaRunId, event, true);
        }
        return publicEvent(javaRunId, event, true);
    }

    /** Controller须先提交project事务；原run关联、捕获登录及会话拥有关系再次核验。 */
    public com.aiep.platformai.api.dto.MemoryResumeReceipt onMemoryWait(String javaRunId,CustomerServiceRunEvent event,
            com.aiep.aihub.application.operation.OperationActor capturedActor) {
        if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())
            throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_REFRESH_TRANSACTION_INVALID");
        String ref=memoryWaitReference(event);
        if(actors==null||memoryResumes==null)throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_REFRESH_CAPABILITY_UNSUPPORTED");
        var actor=actors.revalidate(capturedActor);var run=repository.findRun(javaRunId,actor.tenantId());
        if(run==null||!actor.tenantId().equals(run.tenantId())||!event.runId().equals(run.agentRunId())||run.lastEventSequence()<event.sequence())
            throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_RESUME_CONFLICT");
        var conversation=repository.findConversation(run.conversationId(),actor.tenantId(),actor.userId());
        if(conversation==null||!actor.tenantId().equals(conversation.tenantId())||!actor.userId().equals(conversation.userId()))
            throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_SCOPE_DENIED");
        if(com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))
            throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("ACCESS_REVOKED");
        return memoryResumes.onWaitEvent(run.tenantId(),run.id(),run.agentRunId(),ref);
    }
    private static String memoryWaitReference(CustomerServiceRunEvent event) {
        if(!"context_refresh_required".equals(event.eventType())||event.payload().contextWaitRef()==null)
            throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_WAIT_EVENT_INVALID");
        return event.payload().contextWaitRef();
    }
    /** 原内部通知只refs，事务外执行原唯一derive，员工SSE不暴露baseline/计划。 */
    public void onMemoryDerive(String javaRunId,CustomerServiceRunEvent event,com.aiep.aihub.application.operation.OperationActor captured) {
        if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("DERIVE_OUTSIDE_TRANSACTION_REQUIRED");
        var refs=memoryDeriveReferences(event);if(actors==null||memoryDerives==null||memoryPackets==null)throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_DERIVE_FEATURE_DISABLED");
        var actor=actors.revalidate(captured);var run=repository.findRun(javaRunId,actor.tenantId());
        if(run==null||!event.runId().equals(run.agentRunId())||run.lastEventSequence()<event.sequence())throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("DERIVE_BINDING_CONFLICT");
        if(com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))return;
        var conversation=repository.findConversation(run.conversationId(),actor.tenantId(),actor.userId());if(conversation==null)throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("MEMORY_SCOPE_DENIED");
        var scope=memoryPackets.issuedScope(actor.tenantId(),javaRunId);
        if(!"customer-service".equals(scope.domain())||!scope.userId().equals(actor.userId())||!scope.sessionId().equals(run.conversationId()))throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("DERIVE_SCOPE_MISMATCH");
        memoryDerives.handlePendingDerive(actor,scope,javaRunId,run.agentRunId(),refs.get(0),refs.get(1));
    }
    private static java.util.List<String> memoryDeriveReferences(CustomerServiceRunEvent event) {
        var payload=event.payload();
        if(!"memory_derive_required".equals(event.eventType())||payload.derivePlanId()==null||payload.deriveBaselineRef()==null||payload.contextWaitRef()!=null||payload.delta()!=null||payload.citation()!=null)throw new com.aiep.aihub.api.memory.MemoryContracts.MemoryException("DERIVE_BINDING_CONFLICT");
        com.aiep.aihub.repository.memory.MemoryMapper.identity(payload.derivePlanId());com.aiep.aihub.repository.memory.MemoryMapper.identity(payload.deriveBaselineRef());return java.util.List.of(payload.derivePlanId(),payload.deriveBaselineRef());
    }

    public java.util.List<PublicEvent> replay(String javaRunId, String tenantId, long afterSequence) {
        RunPO run = repository.findRun(javaRunId, tenantId);
        if (run == null) throw new IllegalArgumentException("CUSTOMER_SERVICE_RUN_NOT_FOUND");
        if(memoryPackets!=null&&memoryPackets.enabled()
                &&(memoryAgentPolicies==null||memoryAgentPolicies.privateMemoryDomain(tenantId,"customer-service")||memoryPackets.hasIssuedExecution(tenantId,javaRunId))) {
            var scope=memoryPackets.issuedScope(tenantId,javaRunId);memoryPackets.validateKnowledgePublication(scope,javaRunId);
            memoryPackets.verifyManifest(scope,javaRunId,run.agentRunId(),ai.queryMemoryManifest(tenantId,javaRunId));
        }
        if (!com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))
            throw new IllegalArgumentException("CUSTOMER_SERVICE_RUN_NOT_TERMINAL");
        java.util.List<PublicEvent> result = new java.util.ArrayList<>();
        for (RunStepPO step : repository.listRunSteps(javaRunId).stream()
                .sorted(java.util.Comparator.comparingLong(RunStepPO::sequenceNo)).toList()) {
            if (!javaRunId.equals(step.runId()) || step.sequenceNo() <= afterSequence
                    || step.sequenceNo() > run.lastEventSequence() || step.internalPayload() == null) continue;
            try {
                var node = objectMapper.readTree(step.internalPayload());
                if (!node.isObject()) continue;
                var payloadNode = ((com.fasterxml.jackson.databind.node.ObjectNode) node).deepCopy();
                String type = payloadNode.path("_event_type").asText("");
                payloadNode.remove("_event_type");
                var payload = objectMapper.treeToValue(payloadNode, CustomerServiceRunEvent.Payload.class);
                if("context_refresh_required".equals(type)||"memory_derive_required".equals(type)||payload.contextWaitRef()!=null||payload.derivePlanId()!=null)continue;
                if (type.isEmpty()) type = legacyEventType(step, payload);
                if (type == null) continue;
                var status = com.aiep.platformai.api.dto.CustomerServiceRunView.Status.valueOf(step.status());
                if (("answer.completed".equals(type) && !"SUCCEEDED".equals(step.status()))
                        || ("run.failed".equals(type) && !java.util.Set.of("FAILED", "TIMED_OUT").contains(step.status()))
                        || ("run.cancelled".equals(type) && !"CANCELLED".equals(step.status()))) continue;
                if ("citation.ready".equals(type)) {
                    if (payload.citation() == null) continue;
                    CitationPO citation = repository.findCitationByRunAndNumber(javaRunId, payload.citation().citationNo());
                    if (citation != null && javaRunId.equals(citation.runId()))
                        result.add(new PublicEvent(step.sequenceNo(), type, citation));
                    continue;
                }
                if (!java.util.Set.of("run.started", "stage.started", "stage.completed", "conversation.title",
                        "answer.delta", "answer.completed", "run.failed", "run.cancelled", "retrieval.snapshot").contains(type)) continue;
                if (java.util.Set.of("stage.started", "stage.completed", "run.started").contains(type)
                        && payload.phase() == null) continue;
                if ("retrieval.snapshot".equals(type)) continue;
                var event = new CustomerServiceRunEvent("customer-service-run-event/1", value(run.agentRunId()),
                        step.sequenceNo(), type, status, step.startedAt(), payload);
                result.add(publicEvent(javaRunId, event, false));
            } catch (JsonProcessingException | IllegalArgumentException ignored) {
                // 损坏或无法识别的历史内部载荷不进入员工公开流，也不据运行状态补造终态。
            }
        }
        return java.util.List.copyOf(result);
    }

    private static String legacyEventType(RunStepPO step, CustomerServiceRunEvent.Payload payload) {
        if (step.stage() == null) return null;
        return switch (step.stage()) {
            case "answer.delta", "citation.ready", "answer.completed", "run.failed", "run.cancelled" -> step.stage();
            case "failed" -> "run.failed";
            case "cancelled" -> "run.cancelled";
            case "conversation_title" -> "conversation.title";
            case "retrieval_snapshot" -> "retrieval.snapshot";
            case "intent", "retrieval", "verification", "answer" -> payload.phase() == null ? null
                    : "STARTED".equals(payload.phase()) ? "stage.started" : "stage.completed";
            default -> null;
        };
    }

    private String eventJson(CustomerServiceRunEvent event) {
        var node = objectMapper.valueToTree(event.payload());
        ((com.fasterxml.jackson.databind.node.ObjectNode) node).put("_event_type", event.eventType());
        return safeJson(node);
    }

    private PublicEvent publicEvent(String javaRunId, CustomerServiceRunEvent event, boolean newlyProjected) {
        if("context_refresh_required".equals(event.eventType())||"memory_derive_required".equals(event.eventType()))return null;
        if ("conversation.title".equals(event.eventType()))
            return new PublicEvent(event.sequence(), "run.progress", Map.of("stage", "conversation_title", "summary", "会话标题已更新"));
        if ("answer.delta".equals(event.eventType()))
            return new PublicEvent(event.sequence(), "message.delta", Map.of("delta", value(event.payload().delta())));
        if ("citation.ready".equals(event.eventType()) && event.payload().citation() != null) {
            var value = newlyProjected ? null : repository.findCitationByRunAndNumber(javaRunId, event.payload().citation().citationNo());
            return new PublicEvent(event.sequence(), "citation.ready", value == null ? event.payload().citation() : value);
        }
        if ("answer.completed".equals(event.eventType()))
            return new PublicEvent(event.sequence(), "run.completed", Map.of("answerMode", value(event.payload().answerMode())));
        if ("run.failed".equals(event.eventType()))
            return new PublicEvent(event.sequence(), "run.failed", Map.of("errorCode", value(event.payload().errorCode()), "errorMessage", value(event.payload().errorMessage())));
        if ("run.cancelled".equals(event.eventType())) return new PublicEvent(event.sequence(), "run.cancelled", Map.of());
        String type = "run.started".equals(event.eventType()) ? "run.started" : "run.progress";
        String phase = event.payload().phase();
        if (phase != null) {
            return new PublicEvent(event.sequence(), type, Map.of(
                    "stage", value(event.payload().stage()), "phase", phase,
                    "summary", publicStageSummary(event.payload().stage(), phase, event.payload().publicSummary())));
        }
        return new PublicEvent(event.sequence(), type, Map.of("stage", value(event.payload().stage()), "summary", value(event.payload().publicSummary())));
    }

    static String publicStageSummary(String stage, String phase) {
        return switch (stage + "/" + phase) {
            case "intent/STARTED" -> "正在理解问题";
            case "intent/COMPLETED" -> "已理解问题";
            case "retrieval/STARTED" -> "正在查找公司资料";
            case "retrieval/COMPLETED" -> "资料查找完成";
            case "verification/STARTED" -> "正在核对资料依据";
            case "verification/COMPLETED" -> "依据核对完成";
            case "answer/STARTED" -> "正在撰写回答";
            default -> throw new IllegalArgumentException("CUSTOMER_SERVICE_PUBLIC_STAGE_INVALID");
        };
    }

    static String publicStageSummary(String stage, String phase, String requestedSummary) {
        if ("answer".equals(stage) && "STARTED".equals(phase)
                && ("公司资料存在缺口，正在整理通用建议".equals(requestedSummary)
                    || "正在整理已有公司依据与通用建议".equals(requestedSummary))) {
            return requestedSummary;
        }
        return publicStageSummary(stage, phase);
    }

    private static String value(String input) { return input == null ? "" : input; }

    private String safeJson(Object value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (JsonProcessingException error) { throw new IllegalArgumentException("CUSTOMER_SERVICE_EVENT_JSON_INVALID", error); }
    }

    public record PublicEvent(long sequence, String eventType, Object payload) { }
}
