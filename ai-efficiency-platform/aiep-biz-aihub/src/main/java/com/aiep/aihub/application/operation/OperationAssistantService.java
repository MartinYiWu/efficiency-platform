package com.aiep.aihub.application.operation;

import com.aiep.aihub.repository.operation.OperationArtifactMapper;
import com.aiep.aihub.repository.operation.OperationArtifactPO;
import com.aiep.aihub.repository.operation.OperationConversationMapper;
import com.aiep.aihub.repository.operation.OperationConversationPO;
import com.aiep.aihub.repository.operation.OperationMessageMapper;
import com.aiep.aihub.repository.operation.OperationMessagePO;
import com.aiep.aihub.repository.operation.OperationRunMapper;
import com.aiep.aihub.repository.operation.OperationRunPO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.OperationAgentCancelResponse;
import com.aiep.platformai.api.dto.OperationAgentArtifactContext;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformai.api.dto.OperationAgentRunResponse;
import com.aiep.platformai.agent.AgentTransportException;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.type.TypeReference;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

@Service
public class OperationAssistantService {
    private static final Logger log = LoggerFactory.getLogger(OperationAssistantService.class);
    private static final Set<String> TERMINAL_STATUSES = Set.of("succeeded", "failed", "cancelled", "timed_out");
    private final OperationConversationMapper conversationMapper;
    private final OperationMessageMapper messageMapper;
    private final OperationRunMapper runMapper;
    private final OperationArtifactMapper artifactMapper;
    private final AiInvokeFacade aiInvokeFacade;
    private final ObjectMapper objectMapper;

    public OperationAssistantService(
            OperationConversationMapper conversationMapper,
            OperationMessageMapper messageMapper,
            OperationRunMapper runMapper,
            OperationArtifactMapper artifactMapper,
            AiInvokeFacade aiInvokeFacade,
            ObjectMapper objectMapper) {
        this.conversationMapper = conversationMapper;
        this.messageMapper = messageMapper;
        this.runMapper = runMapper;
        this.artifactMapper = artifactMapper;
        this.aiInvokeFacade = aiInvokeFacade;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public OperationViews.ConversationView createConversation(String requestedTitle) {
        OperationActor actor = OperationActor.developmentActor();
        LocalDateTime now = LocalDateTime.now();
        OperationConversationPO conversation = new OperationConversationPO();
        conversation.setId(UUID.randomUUID().toString());
        conversation.setTenantId(actor.tenantId());
        conversation.setUserId(actor.userId());
        conversation.setTitle(normalizeTitle(requestedTitle));
        conversation.setStatus("active");
        conversation.setCreatedAt(now);
        conversation.setUpdatedAt(now);
        conversationMapper.insert(conversation);
        return toConversationView(conversation);
    }

    @Transactional(noRollbackFor = AgentTransportException.class)
    public OperationViews.RunView submitMessage(
            String conversationId, String message, String clientRequestId) {
        long startedAt = System.nanoTime();
        OperationActor actor = OperationActor.developmentActor();
        OperationConversationPO conversation = ownedConversation(conversationId, actor);
        log.info("event=operation_submit_started conversationId={} clientRequestId={}",
                conversationId, clientRequestId);
        OperationMessagePO duplicate = messageMapper.selectOne(new LambdaQueryWrapper<OperationMessagePO>()
                .eq(OperationMessagePO::getTenantId, actor.tenantId())
                .eq(OperationMessagePO::getClientRequestId, clientRequestId)
                .last("LIMIT 1"));
        if (duplicate != null) {
            OperationRunPO priorRun = runMapper.selectOne(new LambdaQueryWrapper<OperationRunPO>()
                    .eq(OperationRunPO::getUserMessageId, duplicate.getId())
                    .last("LIMIT 1"));
            if (priorRun == null) {
                throw new OperationAssistantException("IDEMPOTENCY_STATE_INVALID", "幂等请求状态不完整");
            }
            log.info("event=operation_submit_deduplicated conversationId={} runId={} agentRunId={} status={}",
                    conversationId, priorRun.getId(), priorRun.getAgentRunId(), priorRun.getStatus());
            return toRunView(priorRun);
        }

        LocalDateTime now = LocalDateTime.now();
        OperationMessagePO userMessage = new OperationMessagePO();
        userMessage.setId(UUID.randomUUID().toString());
        userMessage.setConversationId(conversationId);
        userMessage.setTenantId(actor.tenantId());
        userMessage.setRole("user");
        userMessage.setContent(requireText(message, "消息不能为空"));
        userMessage.setClientRequestId(requireText(clientRequestId, "clientRequestId不能为空"));
        userMessage.setCreatedAt(now);
        messageMapper.insert(userMessage);

        OperationRunPO run = new OperationRunPO();
        run.setId(UUID.randomUUID().toString());
        run.setConversationId(conversationId);
        run.setTenantId(actor.tenantId());
        run.setUserMessageId(userMessage.getId());
        run.setStatus("submitting");
        run.setLastEventSequence(0);
        run.setCreatedAt(now);
        run.setUpdatedAt(now);
        runMapper.insert(run);
        userMessage.setRunId(run.getId());
        messageMapper.updateById(userMessage);

        try {
            OperationAgentRunResponse submitted = aiInvokeFacade.submitOperationMessage(
                    conversationId,
                    new OperationAgentMessageRequest(
                            message,
                            clientRequestId,
                            actor.userId(),
                            availableArtifactContexts(conversationId, actor.tenantId()),
                            actor.tenantId()));
            run.setAgentRunId(submitted.runId());
            run.setStatus(submitted.status());
            run.setUpdatedAt(LocalDateTime.now());
            runMapper.updateById(run);
            log.info("event=operation_agent_run_bound conversationId={} runId={} agentRunId={} status={}",
                    conversationId, run.getId(), run.getAgentRunId(), run.getStatus());
        } catch (AgentTransportException exception) {
            run.setStatus("failed");
            run.setFailureCode(exception.getErrorCode());
            run.setFailureMessage(exception.getMessage());
            run.setUpdatedAt(LocalDateTime.now());
            runMapper.updateById(run);
            log.error("event=operation_submit_failed conversationId={} runId={} code={} httpStatus={} elapsedMs={}",
                    conversationId, run.getId(), exception.getErrorCode(), exception.getStatusCode(),
                    elapsedMillis(startedAt));
            throw exception;
        }

        conversation.setUpdatedAt(now);
        if (conversation.getTitle() == null || conversation.getTitle().isBlank()) {
            conversation.setTitle(normalizeTitle(message));
        }
        conversationMapper.updateById(conversation);
        log.info("event=operation_submit_succeeded conversationId={} runId={} agentRunId={} status={} elapsedMs={}",
                conversationId, run.getId(), run.getAgentRunId(), run.getStatus(), elapsedMillis(startedAt));
        return toRunView(run);
    }

    public Flux<OperationAgentRunEvent> streamRunEvents(String runId, long afterSequence) {
        OperationRunPO run = ownedRun(runId);
        if (run.getAgentRunId() == null) {
            throw new OperationAssistantException("RUN_NOT_STREAMABLE", "运行任务未成功提交到Agent");
        }
        long cursor = Math.max(afterSequence, run.getLastEventSequence());
        return aiInvokeFacade.streamOperationRunEvents(run.getAgentRunId(), run.getTenantId(), cursor)
                .doOnSubscribe(ignored -> log.info(
                        "event=operation_sse_opened runId={} agentRunId={} afterSequence={}",
                        run.getId(), run.getAgentRunId(), cursor))
                .doOnComplete(() -> log.info(
                        "event=operation_sse_completed runId={} agentRunId={}",
                        run.getId(), run.getAgentRunId()))
                .doOnError(error -> log.error(
                        "event=operation_sse_failed runId={} agentRunId={} errorType={}",
                        run.getId(), run.getAgentRunId(), error.getClass().getSimpleName()));
    }

    @Transactional
    public void projectEvent(String runId, OperationAgentRunEvent event) {
        OperationRunPO run = ownedRunForUpdate(runId);
        if (!run.getAgentRunId().equals(event.runId())) {
            throw new OperationAssistantException("RUN_EVENT_MISMATCH", "运行事件标识不匹配");
        }
        if (TERMINAL_STATUSES.contains(run.getStatus())) {
            log.info("event=operation_event_ignored_terminal runId={} agentRunId={} sequence={} event={} status={}",
                    run.getId(), run.getAgentRunId(), event.sequence(), event.event(), run.getStatus());
            return;
        }
        if (event.sequence() <= run.getLastEventSequence()) {
            log.warn("event=operation_event_ignored runId={} agentRunId={} sequence={} lastSequence={}",
                    run.getId(), run.getAgentRunId(), event.sequence(), run.getLastEventSequence());
            return;
        }
        run.setLastEventSequence(event.sequence());
        run.setUpdatedAt(LocalDateTime.now());
        if ("run_started".equals(event.event())) {
            run.setStatus("running");
        } else if ("clarification_required".equals(event.event())) {
            run.setStatus("waiting_input");
            persistAssistantDelta(run, stringValue(event.payload().get("question")));
        } else if ("stream_error".equals(event.event())) {
            run.setFailureCode(stringValue(event.payload().get("code")));
            run.setFailureMessage(stringValue(event.payload().get("safe_message")));
        } else if ("assistant_delta".equals(event.event())) {
            persistAssistantDelta(run, stringValue(event.payload().get("delta")));
        } else if ("deliverable".equals(event.event())) {
            persistDeliverables(run, event.payload());
        } else if ("stream_done".equals(event.event())) {
            run.setStatus(stringValue(event.payload().get("status")));
        }
        runMapper.updateById(run);
        log.info("event=operation_event_projected runId={} agentRunId={} sequence={} event={} status={}",
                run.getId(), run.getAgentRunId(), event.sequence(), event.event(), run.getStatus());
        if ("stream_done".equals(event.event())) {
            log.info("event=operation_run_terminal runId={} agentRunId={} sequence={} status={}",
                    run.getId(), run.getAgentRunId(), event.sequence(), run.getStatus());
        }
    }

    @Transactional
    public void failEventProjection(String runId, OperationAgentRunEvent event, Exception exception) {
        OperationRunPO run = ownedRunForUpdate(runId);
        if (TERMINAL_STATUSES.contains(run.getStatus())) {
            return;
        }
        run.setStatus("failed");
        run.setFailureCode("EVENT_PROJECTION_FAILED");
        run.setFailureMessage("运行结果持久化失败，请稍后重试");
        run.setLastEventSequence(Math.max(run.getLastEventSequence(), event.sequence()));
        run.setUpdatedAt(LocalDateTime.now());
        runMapper.updateById(run);
        log.error("event=operation_event_projection_failed runId={} agentRunId={} sequence={} event={} errorType={}",
                run.getId(), run.getAgentRunId(), event.sequence(), event.event(), exception.getClass().getSimpleName());
    }

    @Transactional
    public OperationViews.RunView cancelRun(String runId) {
        OperationRunPO run = ownedRunForUpdate(runId);
        if (run.getAgentRunId() == null) {
            throw new OperationAssistantException("RUN_NOT_CANCELLABLE", "运行任务未成功提交到Agent");
        }
        if (TERMINAL_STATUSES.contains(run.getStatus())) {
            return toRunView(run);
        }
        OperationAgentCancelResponse cancelled = aiInvokeFacade.cancelOperationRun(run.getAgentRunId(), run.getTenantId());
        String persistedStatus = TERMINAL_STATUSES.contains(cancelled.status()) ? cancelled.status() : "cancelled";
        run.setStatus(persistedStatus);
        run.setUpdatedAt(LocalDateTime.now());
        runMapper.updateById(run);
        log.info("event=operation_cancel_result runId={} agentRunId={} agentStatus={} status={}",
                run.getId(), run.getAgentRunId(), cancelled.status(), run.getStatus());
        return toRunView(run);
    }

    public OperationViews.ConversationView getConversation(String conversationId) {
        return toConversationView(ownedConversation(conversationId, OperationActor.developmentActor()));
    }

    public OperationViews.MessageListView listMessages(String conversationId) {
        OperationActor actor = OperationActor.developmentActor();
        ownedConversation(conversationId, actor);
        List<OperationViews.MessageView> messages = messageMapper
                .selectConversationMessages(conversationId, actor.tenantId())
                .stream()
                .map(message -> new OperationViews.MessageView(
                        message.getId(), message.getRole(), message.getContent(),
                        message.getRunId(), message.getCreatedAt()))
                .toList();
        return new OperationViews.MessageListView(conversationId, messages);
    }

    public OperationViews.ArtifactView getArtifact(String artifactId) {
        OperationArtifactPO artifact = ownedArtifact(artifactId);
        return toArtifactView(artifact);
    }

    public OperationViews.RunView getRun(String runId) {
        return toRunView(ownedRun(runId));
    }

    public OperationViews.ArtifactListView listArtifacts(String conversationId) {
        OperationActor actor = OperationActor.developmentActor();
        ownedConversation(conversationId, actor);
        List<OperationViews.ArtifactSummary> items = artifactMapper.selectList(
                        new LambdaQueryWrapper<OperationArtifactPO>()
                                .eq(OperationArtifactPO::getConversationId, conversationId)
                                .eq(OperationArtifactPO::getTenantId, actor.tenantId())
                                .orderByAsc(OperationArtifactPO::getCreatedAt))
                .stream()
                .map(item -> new OperationViews.ArtifactSummary(
                        item.getId(), item.getArtifactType(), item.getPlatform(), item.getVersionNo(),
                        item.getTitle(), item.getCreatedAt()))
                .toList();
        return new OperationViews.ArtifactListView(conversationId, items);
    }

    private void persistDeliverables(OperationRunPO run, Map<String, Object> payload) {
        Object rawSet = payload.get("deliverable_set");
        if (!(rawSet instanceof Map<?, ?> rawMap)) {
            throw new OperationAssistantException("DELIVERABLE_INVALID", "交付结果格式无效");
        }
        Map<String, Object> deliverableSet = stringKeyMap(rawMap);
        Object rawDeliverables = deliverableSet.get("deliverables");
        if (!(rawDeliverables instanceof List<?> list)) {
            throw new OperationAssistantException("DELIVERABLE_INVALID", "交付结果缺少内容列表");
        }
        OperationConversationPO conversation = conversationMapper.selectById(run.getConversationId());
        List<OperationArtifactPO> artifacts = new ArrayList<>();
        boolean researchProduced = false;
        for (Object rawItem : list) {
            if (!(rawItem instanceof Map<?, ?> itemMap)) {
                continue;
            }
            Map<String, Object> item = stringKeyMap(itemMap);
            String artifactType = firstNonBlank(
                    item,
                    "deliverable_kind",
                    "kind",
                    contentKind(item, "platform_content"));
            String platform = firstNonBlank(item, "platform", null, "generic");
            String title = firstNonBlank(item, "title", null, "运营成稿");
            String body = extractBody(item);
            OperationArtifactPO artifact = new OperationArtifactPO();
            artifact.setId(UUID.randomUUID().toString());
            artifact.setConversationId(run.getConversationId());
            artifact.setRunId(run.getId());
            artifact.setTenantId(run.getTenantId());
            artifact.setArtifactType(artifactType);
            artifact.setScenario(firstNonBlank(item, "scenario", "deliverable_kind", artifactType));
            artifact.setPlatform(platform);
            OperationArtifactPO previous = latestArtifact(run.getConversationId(), artifactType, platform);
            artifact.setVersionNo(previous == null ? 1 : previous.getVersionNo() + 1);
            artifact.setParentArtifactId(previous == null ? null : previous.getId());
            artifact.setRootArtifactId(previous == null ? artifact.getId() : previous.getRootArtifactId());
            artifact.setTitle(title);
            artifact.setBodyMarkdown(body);
            artifact.setBodyHtml(SafeMarkdownRenderer.render(body));
            artifact.setPublicContent(writeJson(item));
            artifact.setCreatedAt(LocalDateTime.now());
            if ("ranked_digest".equals(artifactType)) {
                artifact.setSourceResearchRunId(run.getId());
                researchProduced = true;
            } else {
                artifact.setSourceResearchRunId(conversation.getLastResearchRunId());
            }
            Object provenance = deliverableSet.get("provenance");
            artifact.setInternalMetadata(writeJson(Map.of(
                    "deliverable", item,
                    "provenance", provenance == null ? Map.of() : provenance,
                    "agentRunId", run.getAgentRunId())));
            artifactMapper.insert(artifact);
            artifacts.add(artifact);
        }
        if (artifacts.isEmpty()) {
            throw new OperationAssistantException("DELIVERABLE_EMPTY", "交付结果为空");
        }
        if (researchProduced) {
            conversation.setLastResearchRunId(run.getId());
            conversation.setUpdatedAt(LocalDateTime.now());
            conversationMapper.updateById(conversation);
        }
        persistAssistantMessage(run, artifacts);
        log.info("event=operation_artifacts_persisted runId={} agentRunId={} count={} types={}",
                run.getId(), run.getAgentRunId(), artifacts.size(), artifacts.stream()
                        .map(OperationArtifactPO::getArtifactType).distinct().sorted().toList());
    }

    private void persistAssistantMessage(OperationRunPO run, List<OperationArtifactPO> artifacts) {
        String content = artifacts.stream()
                .map(OperationArtifactPO::getBodyMarkdown)
                .reduce((a, b) -> a + "\n\n" + b)
                .orElse("");
        OperationMessagePO message = assistantMessage(run);
        if (message == null) {
            message = newAssistantMessage(run, content);
            messageMapper.insert(message);
        } else {
            message.setContent(content);
            messageMapper.updateById(message);
        }
    }

    private void persistAssistantDelta(OperationRunPO run, String delta) {
        if (delta == null || delta.isEmpty()) {
            return;
        }
        OperationMessagePO message = assistantMessage(run);
        if (message == null) {
            messageMapper.insert(newAssistantMessage(run, delta));
        } else {
            message.setContent(message.getContent() + delta);
            messageMapper.updateById(message);
        }
    }

    private OperationMessagePO assistantMessage(OperationRunPO run) {
        return messageMapper.selectOne(new LambdaQueryWrapper<OperationMessagePO>()
                .eq(OperationMessagePO::getTenantId, run.getTenantId())
                .eq(OperationMessagePO::getRunId, run.getId())
                .eq(OperationMessagePO::getRole, "assistant")
                .last("LIMIT 1"));
    }

    private OperationMessagePO newAssistantMessage(OperationRunPO run, String content) {
        OperationMessagePO message = new OperationMessagePO();
        message.setId(UUID.randomUUID().toString());
        message.setConversationId(run.getConversationId());
        message.setTenantId(run.getTenantId());
        message.setRole("assistant");
        message.setContent(content);
        message.setRunId(run.getId());
        message.setCreatedAt(LocalDateTime.now());
        return message;
    }

    private OperationArtifactPO latestArtifact(String conversationId, String artifactType, String platform) {
        return artifactMapper.selectOne(new LambdaQueryWrapper<OperationArtifactPO>()
                .eq(OperationArtifactPO::getConversationId, conversationId)
                .eq(OperationArtifactPO::getArtifactType, artifactType)
                .eq(OperationArtifactPO::getPlatform, platform)
                .orderByDesc(OperationArtifactPO::getVersionNo)
                .last("LIMIT 1"));
    }

    private List<OperationAgentArtifactContext> availableArtifactContexts(
            String conversationId, String tenantId) {
        List<OperationArtifactPO> rows = artifactMapper.selectList(
                new LambdaQueryWrapper<OperationArtifactPO>()
                        .eq(OperationArtifactPO::getConversationId, conversationId)
                        .eq(OperationArtifactPO::getTenantId, tenantId)
                        .orderByDesc(OperationArtifactPO::getCreatedAt));
        Map<String, OperationArtifactPO> latestByRoot = new LinkedHashMap<>();
        for (OperationArtifactPO row : rows) {
            latestByRoot.putIfAbsent(row.getRootArtifactId(), row);
            if (latestByRoot.size() == 8) {
                break;
            }
        }
        return latestByRoot.values().stream()
                .map(row -> new OperationAgentArtifactContext(
                        row.getId(),
                        row.getRootArtifactId(),
                        row.getVersionNo(),
                        row.getArtifactType(),
                        row.getScenario(),
                        row.getPlatform(),
                        row.getTitle(),
                        parsePublicContent(row.getPublicContent()),
                        row.getBodyMarkdown()))
                .toList();
    }

    private Map<String, Object> parsePublicContent(String value) {
        try {
            return objectMapper.readValue(value, new TypeReference<>() { });
        } catch (JsonProcessingException exception) {
            throw new OperationAssistantException("ARTIFACT_CONTEXT_INVALID", "历史交付物格式无效");
        }
    }

    private String extractBody(Map<String, Object> item) {
        Object contentValue = item.get("content");
        if (contentValue instanceof Map<?, ?> contentMap) {
            Object markdown = contentMap.get("body_markdown");
            if (markdown instanceof String body && !body.isBlank()) {
                return body;
            }
        }
        Object copyText = item.get("copy_text");
        if (copyText instanceof String body && !body.isBlank()) {
            return body;
        }
        Object bodyValue = item.get("body");
        if (bodyValue instanceof String body && !body.isBlank()) {
            return body;
        }
        throw new OperationAssistantException("DELIVERABLE_BODY_EMPTY", "交付正文为空");
    }

    private static String contentKind(Map<String, Object> item, String fallback) {
        Object contentValue = item.get("content");
        if (contentValue instanceof Map<?, ?> contentMap) {
            Object kind = contentMap.get("kind");
            if (kind instanceof String text && !text.isBlank()) {
                return text;
            }
        }
        return fallback;
    }

    private OperationConversationPO ownedConversation(String id, OperationActor actor) {
        OperationConversationPO value = conversationMapper.selectOne(new LambdaQueryWrapper<OperationConversationPO>()
                .eq(OperationConversationPO::getId, id)
                .eq(OperationConversationPO::getTenantId, actor.tenantId())
                .eq(OperationConversationPO::getUserId, actor.userId())
                .last("LIMIT 1"));
        if (value == null) {
            throw new OperationAssistantException("CONVERSATION_NOT_FOUND", "会话不存在");
        }
        return value;
    }

    private OperationRunPO ownedRun(String id) {
        OperationActor actor = OperationActor.developmentActor();
        OperationRunPO value = runMapper.selectOne(new LambdaQueryWrapper<OperationRunPO>()
                .eq(OperationRunPO::getId, id)
                .eq(OperationRunPO::getTenantId, actor.tenantId())
                .last("LIMIT 1"));
        if (value == null) {
            throw new OperationAssistantException("RUN_NOT_FOUND", "运行记录不存在");
        }
        ownedConversation(value.getConversationId(), actor);
        return value;
    }

    private OperationRunPO ownedRunForUpdate(String id) {
        OperationActor actor = OperationActor.developmentActor();
        OperationRunPO value = runMapper.selectForUpdate(id, actor.tenantId());
        if (value == null) {
            throw new OperationAssistantException("RUN_NOT_FOUND", "运行记录不存在");
        }
        ownedConversation(value.getConversationId(), actor);
        return value;
    }

    private OperationArtifactPO ownedArtifact(String id) {
        OperationActor actor = OperationActor.developmentActor();
        OperationArtifactPO value = artifactMapper.selectOne(new LambdaQueryWrapper<OperationArtifactPO>()
                .eq(OperationArtifactPO::getId, id)
                .eq(OperationArtifactPO::getTenantId, actor.tenantId())
                .last("LIMIT 1"));
        if (value == null) {
            throw new OperationAssistantException("ARTIFACT_NOT_FOUND", "文章制品不存在");
        }
        ownedConversation(value.getConversationId(), actor);
        return value;
    }

    private OperationViews.ConversationView toConversationView(OperationConversationPO value) {
        return new OperationViews.ConversationView(value.getId(), value.getTitle(), value.getStatus(), value.getCreatedAt());
    }

    private OperationViews.RunView toRunView(OperationRunPO value) {
        return new OperationViews.RunView(
                value.getConversationId(), value.getId(), value.getAgentRunId(), value.getStatus(),
                value.getFailureCode(), value.getFailureMessage(), value.getLastEventSequence());
    }

    private OperationViews.ArtifactView toArtifactView(OperationArtifactPO value) {
        return new OperationViews.ArtifactView(
                value.getId(), value.getConversationId(), value.getRunId(), value.getArtifactType(), value.getScenario(), value.getPlatform(),
                value.getVersionNo(), value.getRootArtifactId(), value.getParentArtifactId(), value.getTitle(), value.getBodyMarkdown(),
                value.getBodyHtml(), value.getPublicContent(), value.getCreatedAt());
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new OperationAssistantException("DELIVERABLE_METADATA_INVALID", "交付元数据无法保存");
        }
    }

    private static Map<String, Object> stringKeyMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        value.forEach((key, item) -> result.put(String.valueOf(key), item));
        return result;
    }

    private static String firstNonBlank(Map<String, Object> value, String first, String second, String fallback) {
        for (String key : second == null ? List.of(first) : List.of(first, second)) {
            Object candidate = value.get(key);
            if (candidate instanceof String text && !text.isBlank()) {
                return text;
            }
        }
        return fallback;
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static String normalizeTitle(String title) {
        if (title == null || title.isBlank()) {
            return null;
        }
        String normalized = title.strip();
        return normalized.length() <= 80 ? normalized : normalized.substring(0, 80);
    }

    private static String requireText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new OperationAssistantException("INVALID_REQUEST", message);
        }
        return value.strip();
    }

    private static long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000L;
    }
}
