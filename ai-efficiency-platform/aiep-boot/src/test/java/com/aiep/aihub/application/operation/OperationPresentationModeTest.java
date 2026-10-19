package com.aiep.aihub.application.operation;

import com.aiep.aihub.repository.operation.OperationArtifactMapper;
import com.aiep.aihub.repository.operation.OperationArtifactPO;
import com.aiep.aihub.repository.operation.OperationConversationMapper;
import com.aiep.aihub.repository.operation.OperationConversationPO;
import com.aiep.aihub.repository.operation.OperationMessageMapper;
import com.aiep.aihub.repository.operation.OperationRunMapper;
import com.aiep.aihub.repository.operation.OperationRunPO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformai.api.dto.OperationAgentRunResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OperationPresentationModeTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void inlineModeIsExplicitAndLegacyPayloadDefaultsToArtifact() {
        assertEquals("inline", OperationAssistantService.presentationMode(
                Map.of("presentation_mode", "inline")));
        assertEquals("artifact", OperationAssistantService.presentationMode(Map.of()));
        assertEquals("artifact", OperationAssistantService.presentationMode(
                Map.of("presentation_mode", "unexpected")));
    }

    @Test
    void inlineResearchMetadataIsHiddenButArtifactsAndLegacyRowsRemainPublic() {
        assertFalse(OperationAssistantService.isPublicArtifactMetadata(
                "{\"presentationMode\":\"inline\"}", objectMapper));
        assertTrue(OperationAssistantService.isPublicArtifactMetadata(
                "{\"presentationMode\":\"artifact\"}", objectMapper));
        assertTrue(OperationAssistantService.isPublicArtifactMetadata(
                "{\"agentRunId\":\"legacy\"}", objectMapper));
        assertTrue(OperationAssistantService.isPublicArtifactMetadata(null, objectMapper));
    }

    @Test
    void projectedInlineResearchIsHiddenFromPublicListButRemainsAvailableToNextRequest() {
        OperationConversationMapper conversationMapper = mock(OperationConversationMapper.class);
        OperationMessageMapper messageMapper = mock(OperationMessageMapper.class);
        OperationRunMapper runMapper = mock(OperationRunMapper.class);
        OperationArtifactMapper artifactMapper = mock(OperationArtifactMapper.class);
        AiInvokeFacade aiInvokeFacade = mock(AiInvokeFacade.class);
        List<OperationArtifactPO> storedArtifacts = new ArrayList<>();

        OperationConversationPO conversation = new OperationConversationPO();
        conversation.setId("conversation-1");
        conversation.setTenantId("dev");
        conversation.setUserId("1");
        conversation.setTitle("AI 热点");
        conversation.setStatus("active");
        conversation.setCreatedAt(LocalDateTime.now());
        conversation.setUpdatedAt(LocalDateTime.now());

        OperationRunPO run = new OperationRunPO();
        run.setId("run-1");
        run.setConversationId("conversation-1");
        run.setTenantId("dev");
        run.setAgentRunId("agent-run-1");
        run.setStatus("running");
        run.setLastEventSequence(0);

        when(conversationMapper.selectOne(any())).thenReturn(conversation);
        when(conversationMapper.selectById("conversation-1")).thenReturn(conversation);
        when(runMapper.selectForUpdate("run-1", "dev")).thenReturn(run);
        when(artifactMapper.insert(any(OperationArtifactPO.class))).thenAnswer(invocation -> {
            storedArtifacts.add(invocation.getArgument(0));
            return 1;
        });
        when(artifactMapper.selectList(any())).thenAnswer(ignored -> List.copyOf(storedArtifacts));
        when(aiInvokeFacade.submitOperationMessage(eq("conversation-1"), any()))
                .thenReturn(new OperationAgentRunResponse(
                        "operation-run/1", "conversation-1", "turn-2", "agent-run-2", "queued"));

        OperationAssistantService service = new OperationAssistantService(
                conversationMapper,
                messageMapper,
                runMapper,
                artifactMapper,
                aiInvokeFacade,
                objectMapper);
        Map<String, Object> deliverable = Map.of(
                "deliverable_kind", "ranked_digest",
                "platform", "research",
                "title", "AI 热点汇总",
                "copy_text", "# AI 热点汇总\n\n1. 第一条热点");
        Map<String, Object> payload = Map.of(
                "presentation_mode", "inline",
                "deliverable_set", Map.of(
                        "deliverables", List.of(deliverable),
                        "provenance", Map.of("source_count", 1)));

        service.projectEvent("run-1", new OperationAgentRunEvent(
                "stream-event/1", "deliverable", "agent-run-1", 1, payload));

        assertEquals(1, storedArtifacts.size());
        assertFalse(OperationAssistantService.isPublicArtifactMetadata(
                storedArtifacts.getFirst().getInternalMetadata(), objectMapper));
        assertTrue(service.listArtifacts("conversation-1").artifacts().isEmpty());

        service.submitMessage("conversation-1", "把这些热点写成公众号推文", "request-2");
        ArgumentCaptor<OperationAgentMessageRequest> requestCaptor =
                ArgumentCaptor.forClass(OperationAgentMessageRequest.class);
        verify(aiInvokeFacade).submitOperationMessage(eq("conversation-1"), requestCaptor.capture());
        assertEquals(1, requestCaptor.getValue().artifacts().size());
        assertEquals("ranked_digest", requestCaptor.getValue().artifacts().getFirst().artifactType());
        assertEquals("# AI 热点汇总\n\n1. 第一条热点",
                requestCaptor.getValue().artifacts().getFirst().bodyMarkdown());
    }
}
