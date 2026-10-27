package com.aiep.aihub.application.customer;

import com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.Pending;
import com.aiep.aihub.application.customer.CustomerServiceViews.MessageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.PageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.ReplayView;
import com.aiep.aihub.application.customer.CustomerServiceViews.TimelineView;
import com.aiep.aihub.application.customer.CustomerServiceViews.PublicProgress;
import com.aiep.aihub.application.customer.CustomerServiceViews.SubmitView;
import com.aiep.aihub.domain.customer.CustomerServiceModels;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunView;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

@Service
public class CustomerServiceApplicationService {
    private static final ObjectMapper STAGE_MAPPER = new ObjectMapper();
    private final CustomerServiceMappers repository;
    private final AiManagementMappers management;
    private final CustomerServicePendingRunCreator pendingCreator;
    private final AiInvokeFacade ai;

    public CustomerServiceApplicationService(CustomerServiceMappers repository, AiManagementMappers management,
            CustomerServicePendingRunCreator pendingCreator, AiInvokeFacade ai) {
        this.repository = repository;
        this.management = management;
        this.pendingCreator = pendingCreator;
        this.ai = ai;
    }

    public ConversationPO createConversation(String tenantId, String userId, String title) {
        String normalizedTitle = CustomerServiceConversationTitles.normalize(title, true);
        CustomerServiceConversationTitles.requireAvailable(repository, tenantId, userId, normalizedTitle, null);
        Instant now = Instant.now();
        ConversationPO value = new ConversationPO(UUID.randomUUID().toString(), tenantId, userId,
                normalizedTitle, "ACTIVE", null, now, now);
        try { repository.insertConversation(value); }
        catch (DuplicateKeyException error) { throw CustomerServiceConversationTitles.translate(error); }
        return value;
    }

    public PageView<ConversationPO> listConversations(String tenantId, String userId, String keyword, int page, int pageSize) {
        page = positive(page, "page"); pageSize = range(pageSize, 1, 100, "pageSize");
        return new PageView<>(repository.listConversations(tenantId, userId, keyword, (page - 1) * pageSize, pageSize),
                page, pageSize, repository.countConversations(tenantId, userId, keyword));
    }

    public ConversationPO getConversation(String tenantId, String userId, String id) {
        ConversationPO value = repository.findConversation(id, tenantId, userId);
        if (value == null) throw new IllegalArgumentException("CUSTOMER_SERVICE_CONVERSATION_NOT_FOUND");
        return value;
    }

    public ConversationPO updateConversation(String tenantId, String userId, String id, String title, String status) {
        getConversation(tenantId, userId, id);
        if (status != null && !List.of("ACTIVE", "ARCHIVED").contains(status))
            throw new IllegalArgumentException("CUSTOMER_SERVICE_CONVERSATION_STATUS_INVALID");
        String normalizedTitle = title == null ? null : CustomerServiceConversationTitles.normalize(title, false);
        if (normalizedTitle != null)
            CustomerServiceConversationTitles.requireAvailable(repository, tenantId, userId, normalizedTitle, id);
        try { repository.updateConversation(id, tenantId, userId, normalizedTitle, status); }
        catch (DuplicateKeyException error) { throw CustomerServiceConversationTitles.translate(error); }
        return getConversation(tenantId, userId, id);
    }

    public void deleteConversation(String tenantId, String userId, String id) {
        getConversation(tenantId, userId, id);
        repository.updateConversation(id, tenantId, userId, null, "DELETED");
    }

    public List<MessageView> listMessages(String tenantId, String userId, String conversationId, String before, int limit) {
        getConversation(tenantId, userId, conversationId);
        return repository.listMessages(conversationId, tenantId, before, range(limit, 1, 100, "limit")).stream()
                .map(item -> new MessageView(item, repository.listCitationsByMessage(item.id()))).toList();
    }

    public SubmitView submit(String tenantId, String userId, String conversationId,
            String contractVersion, String message, String clientRequestId) {
        if (!"customer-service-message/1".equals(contractVersion) || message == null || message.isBlank()
                || clientRequestId == null || clientRequestId.isBlank())
            throw new IllegalArgumentException("CUSTOMER_SERVICE_MESSAGE_INVALID");
        getConversation(tenantId, userId, conversationId);
        MessagePO existing = repository.findMessageByClientRequest(tenantId, clientRequestId);
        if (existing != null) {
            RunPO run = repository.findRunByUserMessage(existing.id(), tenantId);
            return new SubmitView(conversationId, run.id(), run.status(), run.agentReleaseId());
        }
        AgentDefinitionPO definition = management.findAgentByKey(CustomerServiceModels.AGENT_KEY);
        AiReleasePO release = definition == null ? null : management.findActiveRelease(definition.id(), "dev");
        if (release == null) throw new IllegalStateException("CUSTOMER_SERVICE_ACTIVE_RELEASE_MISSING");
        List<CustomerServiceRunRequest.HistoryMessage> history = boundedHistory(
                repository.listCompletedHistory(conversationId, tenantId, 12));
        Pending pending = pendingCreator.create(conversationId, tenantId, message, clientRequestId, release.id());
        if (!pending.created())
            return new SubmitView(conversationId, pending.run().id(), pending.run().status(), pending.run().agentReleaseId());
        try {
            CustomerServiceRunView agent = ai.submitCustomerServiceMessage(conversationId,
                    new CustomerServiceRunRequest("customer-service-run/1", pending.run().id(), conversationId,
                            tenantId, userId, release.id(), message, history));
            repository.bindAgentRun(pending.run().id(), agent.runId(), agent.status().name());
            return new SubmitView(conversationId, pending.run().id(), agent.status().name(), release.id());
        } catch (RuntimeException error) {
            repository.advanceRun(pending.run().id(), 0, 0, "FAILED", null,
                    "CUSTOMER_SERVICE_AGENT_UNAVAILABLE", "智能客服暂时不可用");
            repository.completeAssistantMessage(pending.assistantMessage().id(), "", null, "FAILED");
            throw error;
        }
    }

    public RunPO getRun(String tenantId, String runId) {
        RunPO value = repository.findRun(runId, tenantId);
        if (value == null) throw new IllegalArgumentException("CUSTOMER_SERVICE_RUN_NOT_FOUND");
        return value;
    }

    @Transactional(readOnly = true)
    public TimelineView timeline(String tenantId, String userId, String runId) {
        RunPO run = getRun(tenantId, runId);
        getConversation(tenantId, userId, run.conversationId());
        MessagePO answer = repository.findAssistantMessageByRun(runId, tenantId);
        if (answer == null) throw new IllegalStateException("CUSTOMER_SERVICE_ASSISTANT_MESSAGE_MISSING");
        List<PublicProgress> steps = new ArrayList<>();
        for (var step : repository.listRunSteps(runId)) {
            if (step.internalPayload() == null) continue;
            try {
                JsonNode payload = STAGE_MAPPER.readTree(step.internalPayload());
                String stage = payload.path("stage").asText("");
                String phase = payload.path("phase").asText("");
                if (phase.isBlank()) continue;
                String summary = CustomerServiceEventProjector.publicStageSummary(stage, phase, payload.path("public_summary").asText(""));
                steps.add(new PublicProgress(step.sequenceNo(), stage, phase, summary, step.startedAt()));
            } catch (com.fasterxml.jackson.core.JsonProcessingException | IllegalArgumentException ignored) {
                // 历史内部步骤不进入员工公开时间线。
            }
        }
        return new TimelineView(run.id(), run.status(), run.lastEventSequence(),
                new MessageView(answer, repository.listCitationsByMessage(answer.id())), List.copyOf(steps));
    }

    public Flux<CustomerServiceRunEvent> stream(String tenantId, String runId, long afterSequence) {
        RunPO run = getRun(tenantId, runId);
        if (run.agentRunId() == null) throw new IllegalStateException("CUSTOMER_SERVICE_AGENT_RUN_NOT_BOUND");
        return ai.streamCustomerServiceRunEvents(run.agentRunId(), afterSequence);
    }

    public RunPO cancel(String tenantId, String runId) {
        RunPO run = getRun(tenantId, runId);
        if (run.agentRunId() != null && !CustomerServiceModels.TERMINAL_STATUSES.contains(run.status()))
            ai.cancelCustomerServiceRun(run.agentRunId());
        return getRun(tenantId, runId);
    }

    public FeedbackPO feedback(String tenantId, String userId, String messageId, String rating, String reasonCode, String comment) {
        CustomerServiceModels.requireRating(rating, reasonCode, comment);
        MessagePO message = repository.findMessage(messageId, tenantId);
        if (message == null || !"ASSISTANT".equals(message.role()) || !"COMPLETED".equals(message.status()))
            throw new IllegalArgumentException("CUSTOMER_SERVICE_FEEDBACK_MESSAGE_INVALID");
        RunPO run = repository.findRun(message.runId(), tenantId);
        Instant now = Instant.now();
        FeedbackPO current = repository.findFeedback(tenantId, userId, messageId);
        FeedbackPO value = new FeedbackPO(current == null ? UUID.randomUUID().toString() : current.id(),
                message.conversationId(), messageId, run.id(), tenantId, userId, rating, reasonCode, comment,
                current == null ? now : current.createdAt(), now);
        repository.upsertFeedback(value);
        return repository.findFeedback(tenantId, userId, messageId);
    }

    public ReplayView replay(String tenantId, String runId) {
        RunPO run = getRun(tenantId, runId);
        MessagePO question = repository.findMessage(run.userMessageId(), tenantId);
        MessagePO answer = repository.findAssistantMessageByRun(runId, tenantId);
        FeedbackPO feedback = answer == null ? null : repository.findFeedback(tenantId, "1", answer.id());
        return new ReplayView(run, question, answer, repository.listRunSteps(runId),
                answer == null ? List.of() : repository.listCitationsByMessage(answer.id()), feedback);
    }

    public CitationPO citation(String tenantId, String id) {
        CitationPO value = repository.findCitation(id, tenantId);
        if (value == null) throw new IllegalArgumentException("CUSTOMER_SERVICE_CITATION_NOT_FOUND");
        return value;
    }

    private static List<CustomerServiceRunRequest.HistoryMessage> boundedHistory(List<MessagePO> source) {
        List<CustomerServiceRunRequest.HistoryMessage> reversed = new ArrayList<>();
        int characters = 0;
        for (int index = source.size() - 1; index >= 0; index--) {
            MessagePO item = source.get(index);
            if (!List.of("USER", "ASSISTANT").contains(item.role()) || characters + item.content().length() > 12000) continue;
            reversed.add(new CustomerServiceRunRequest.HistoryMessage(item.role().toLowerCase(), item.content()));
            characters += item.content().length();
        }
        java.util.Collections.reverse(reversed);
        return List.copyOf(reversed);
    }
    private static int positive(int value, String name) { if (value < 1) throw new IllegalArgumentException(name); return value; }
    private static int range(int value, int min, int max, String name) { if (value < min || value > max) throw new IllegalArgumentException(name); return value; }
}
