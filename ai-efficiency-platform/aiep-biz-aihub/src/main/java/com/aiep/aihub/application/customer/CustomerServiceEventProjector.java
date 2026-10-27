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
    private final CustomerServiceMappers repository;
    private final ObjectMapper objectMapper;

    public CustomerServiceEventProjector(CustomerServiceMappers repository, ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public PublicEvent project(String javaRunId, String tenantId, CustomerServiceRunEvent event) {
        RunPO run = repository.findRun(javaRunId, tenantId);
        if (run == null || !event.runId().equals(run.agentRunId())) {
            throw new IllegalArgumentException("CUSTOMER_SERVICE_AGENT_RUN_MISMATCH");
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
                event.payload().publicSummary(), safeJson(event.payload()), event.occurredAt(), Instant.now()));
        if ("conversation.title".equals(event.eventType())) {
            CustomerServiceConversationTitles.assignAutomatic(repository, run, event.payload().conversationTitle());
            return publicEvent(javaRunId, event, true);
        }
        MessagePO assistant = repository.findAssistantMessageByRun(javaRunId, tenantId);
        if (assistant == null) throw new IllegalStateException("CUSTOMER_SERVICE_ASSISTANT_MESSAGE_MISSING");
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

    private PublicEvent publicEvent(String javaRunId, CustomerServiceRunEvent event, boolean newlyProjected) {
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
