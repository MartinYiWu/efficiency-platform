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
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformai.api.dto.OperationAgentRunResponse;
import com.aiep.platformai.agent.AgentTransportException;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

@Service
public class OperationAssistantService {
    private static final Logger log = LoggerFactory.getLogger(OperationAssistantService.class);
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
        OperationActor actor = OperationActor.developmentActor();
        OperationConversationPO conversation = ownedConversation(conversationId, actor);
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
                    new OperationAgentMessageRequest(message, clientRequestId, actor.userId(), actor.tenantId()));
            run.setAgentRunId(submitted.runId());
            run.setStatus(submitted.status());
            run.setUpdatedAt(LocalDateTime.now());
            runMapper.updateById(run);
        } catch (AgentTransportException exception) {
            run.setStatus("failed");
            run.setFailureCode(exception.getErrorCode());
            run.setFailureMessage(exception.getMessage());
            run.setUpdatedAt(LocalDateTime.now());
            runMapper.updateById(run);
            log.error("运营Agent提交失败，runId={}, code={}, status={}",
                    run.getId(), exception.getErrorCode(), exception.getStatusCode());
            throw exception;
        }

        conversation.setUpdatedAt(now);
        if (conversation.getTitle() == null || conversation.getTitle().isBlank()) {
            conversation.setTitle(normalizeTitle(message));
        }
        conversationMapper.updateById(conversation);
        return toRunView(run);
    }

    public Flux<OperationAgentRunEvent> streamRunEvents(String runId, long afterSequence) {
        OperationRunPO run = ownedRun(runId);
        if (run.getAgentRunId() == null) {
            throw new OperationAssistantException("RUN_NOT_STREAMABLE", "运行任务未成功提交到Agent");
        }
        long cursor = Math.max(afterSequence, run.getLastEventSequence());
        return aiInvokeFacade.streamOperationRunEvents(run.getAgentRunId(), run.getTenantId(), cursor);
    }

    @Transactional
    public void projectEvent(String runId, OperationAgentRunEvent event) {
        OperationRunPO run = ownedRun(runId);
        if (!run.getAgentRunId().equals(event.runId())) {
            throw new OperationAssistantException("RUN_EVENT_MISMATCH", "运行事件标识不匹配");
        }
        if (event.sequence() <= run.getLastEventSequence()) {
            return;
        }
        run.setLastEventSequence(event.sequence());
        run.setUpdatedAt(LocalDateTime.now());
        if ("run_started".equals(event.event())) {
            run.setStatus("running");
        } else if ("clarification_required".equals(event.event())) {
            run.setStatus("waiting_input");
        } else if ("stream_error".equals(event.event())) {
            run.setFailureCode(stringValue(event.payload().get("code")));
            run.setFailureMessage(stringValue(event.payload().get("safe_message")));
        } else if ("deliverable".equals(event.event())) {
            persistDeliverables(run, event.payload());
        } else if ("stream_done".equals(event.event())) {
            run.setStatus(stringValue(event.payload().get("status")));
        }
        runMapper.updateById(run);
    }

    @Transactional
    public OperationViews.RunView cancelRun(String runId) {
        OperationRunPO run = ownedRun(runId);
        if (run.getAgentRunId() == null) {
            throw new OperationAssistantException("RUN_NOT_CANCELLABLE", "运行任务未成功提交到Agent");
        }
        OperationAgentCancelResponse cancelled = aiInvokeFacade.cancelOperationRun(run.getAgentRunId(), run.getTenantId());
        run.setStatus(cancelled.status());
        run.setUpdatedAt(LocalDateTime.now());
        runMapper.updateById(run);
        return toRunView(run);
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
            String artifactType = firstNonBlank(item, "deliverable_kind", "kind", "platform_content");
            String platform = firstNonBlank(item, "platform", null, "generic");
            String title = firstNonBlank(item, "title", null, "运营成稿");
            String body = extractBody(item);
            OperationArtifactPO artifact = new OperationArtifactPO();
            artifact.setId(UUID.randomUUID().toString());
            artifact.setConversationId(run.getConversationId());
            artifact.setRunId(run.getId());
            artifact.setTenantId(run.getTenantId());
            artifact.setArtifactType(artifactType);
            artifact.setPlatform(platform);
            artifact.setVersionNo(nextArtifactVersion(run.getConversationId(), artifactType));
            artifact.setTitle(title);
            artifact.setBodyMarkdown(body);
            artifact.setBodyHtml(SafeMarkdownRenderer.render(body));
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
    }

    private void persistAssistantMessage(OperationRunPO run, List<OperationArtifactPO> artifacts) {
        OperationMessagePO message = new OperationMessagePO();
        message.setId(UUID.randomUUID().toString());
        message.setConversationId(run.getConversationId());
        message.setTenantId(run.getTenantId());
        message.setRole("assistant");
        message.setContent(artifacts.stream().map(OperationArtifactPO::getBodyMarkdown).reduce((a, b) -> a + "\n\n" + b).orElse(""));
        message.setRunId(run.getId());
        message.setCreatedAt(LocalDateTime.now());
        messageMapper.insert(message);
    }

    private int nextArtifactVersion(String conversationId, String artifactType) {
        OperationArtifactPO previous = artifactMapper.selectOne(new LambdaQueryWrapper<OperationArtifactPO>()
                .eq(OperationArtifactPO::getConversationId, conversationId)
                .eq(OperationArtifactPO::getArtifactType, artifactType)
                .orderByDesc(OperationArtifactPO::getVersionNo)
                .last("LIMIT 1"));
        return previous == null ? 1 : previous.getVersionNo() + 1;
    }

    private String extractBody(Map<String, Object> item) {
        Object contentValue = item.get("content");
        if (contentValue instanceof Map<?, ?> contentMap) {
            Object markdown = contentMap.get("body_markdown");
            if (markdown instanceof String body && !body.isBlank()) {
                return body;
            }
        }
        for (String key : List.of("copy_text", "body")) {
            Object value = item.get(key);
            if (value instanceof String body && !body.isBlank()) {
                return body;
            }
        }
        throw new OperationAssistantException("DELIVERABLE_BODY_EMPTY", "交付正文为空");
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
        return value;
    }

    private OperationViews.ConversationView toConversationView(OperationConversationPO value) {
        return new OperationViews.ConversationView(value.getId(), value.getTitle(), value.getStatus(), value.getCreatedAt());
    }

    private OperationViews.RunView toRunView(OperationRunPO value) {
        return new OperationViews.RunView(
                value.getConversationId(), value.getId(), value.getAgentRunId(), value.getStatus(),
                value.getFailureCode(), value.getFailureMessage());
    }

    private OperationViews.ArtifactView toArtifactView(OperationArtifactPO value) {
        return new OperationViews.ArtifactView(
                value.getId(), value.getConversationId(), value.getRunId(), value.getArtifactType(), value.getPlatform(),
                value.getVersionNo(), value.getTitle(), value.getBodyMarkdown(), value.getBodyHtml(), value.getCreatedAt());
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
}
