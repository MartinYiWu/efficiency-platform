package com.aiep.aihub.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector;
import com.aiep.aihub.application.customer.CustomerServicePendingRunCreator;
import com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.Pending;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunView;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class CustomerServiceApplicationServiceTest {
    private final CustomerServiceMappers repository = mock(CustomerServiceMappers.class);
    private final AiManagementMappers management = mock(AiManagementMappers.class);
    private final CustomerServicePendingRunCreator pendingCreator = mock(CustomerServicePendingRunCreator.class);
    private final AiInvokeFacade ai = mock(AiInvokeFacade.class);
    private CustomerServiceApplicationService service;
    private final Instant now = Instant.parse("2026-10-20T08:00:00Z");

    @BeforeEach
    void setUp() {
        service = new CustomerServiceApplicationService(repository, management, pendingCreator, ai);
        when(repository.findConversation("conversation-1", "dev", "1")).thenReturn(
                new ConversationPO("conversation-1", "dev", "1", "标题", "ACTIVE", now, now, now));
    }

    @Test
    void marksOnlyOwnedConversationDeleted() {
        service.deleteConversation("dev", "1", "conversation-1");
        verify(repository).updateConversation("conversation-1", "dev", "1", null, "DELETED");
        assertThatThrownBy(() -> service.deleteConversation("dev", "other-user", "conversation-1"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void freezesActiveReleaseAndBoundsCompletedHistoryBeforeAgentCall() {
        when(repository.findMessageByClientRequest("dev", "request-1")).thenReturn(null);
        when(management.findAgentByKey("customer-service")).thenReturn(
                new AgentDefinitionPO("agent-1", "customer-service", "客服", "", "CUSTOMER_SERVICE", "ACTIVE", "1", null, "1", null));
        when(management.findActiveRelease("agent-1", "dev")).thenReturn(
                new AiReleasePO("release-1", "agent-1", "version-1", "dev", "ACTIVE", "snapshot-1", "1", LocalDateTime.now(), null, LocalDateTime.now()));
        when(repository.listCompletedHistory("conversation-1", "dev", 12)).thenReturn(List.of(
                message("history-1", "USER", "A".repeat(8000)),
                message("history-2", "ASSISTANT", "B".repeat(6000))));
        RunPO run = run("run-1", null, "PENDING", 0);
        when(pendingCreator.create("conversation-1", "dev", "新问题", "request-1", "release-1"))
                .thenReturn(new Pending(run, message("user-1", "USER", "新问题"), message("answer-1", "ASSISTANT", ""), true));
        when(ai.submitCustomerServiceMessage(eq("conversation-1"), any())).thenReturn(
                new CustomerServiceRunView("customer-service-run-view/1", "agent-run-1", "run-1", CustomerServiceRunView.Status.PENDING));

        var result = service.submit("dev", "1", "conversation-1", "customer-service-message/1", "新问题", "request-1");

        ArgumentCaptor<CustomerServiceRunRequest> request = ArgumentCaptor.forClass(CustomerServiceRunRequest.class);
        verify(ai).submitCustomerServiceMessage(eq("conversation-1"), request.capture());
        assertThat(request.getValue().agentReleaseId()).isEqualTo("release-1");
        assertThat(request.getValue().history()).hasSize(1);
        assertThat(request.getValue().history().stream().mapToInt(item -> item.content().length()).sum()).isLessThanOrEqualTo(12000);
        assertThat(result.status()).isEqualTo("PENDING");
        verify(repository).bindAgentRun("run-1", "agent-run-1", "PENDING");
    }

    @Test
    void returnsOriginalRunForSameClientRequestWithoutSecondAgentCall() {
        MessagePO original = message("user-1", "USER", "问题");
        when(repository.findMessageByClientRequest("dev", "request-1")).thenReturn(original);
        when(repository.findRunByUserMessage("user-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 2));
        var result = service.submit("dev", "1", "conversation-1", "customer-service-message/1", "问题", "request-1");
        assertThat(result.runId()).isEqualTo("run-1");
        verify(ai, never()).submitCustomerServiceMessage(any(), any());
    }

    @Test
    void failedSubmissionDoesNotLeaveAssistantPending() {
        when(management.findAgentByKey("customer-service")).thenReturn(
                new AgentDefinitionPO("agent-1", "customer-service", "客服", "", "CUSTOMER_SERVICE", "ACTIVE", "1", null, "1", null));
        when(management.findActiveRelease("agent-1", "dev")).thenReturn(
                new AiReleasePO("release-1", "agent-1", "version-1", "dev", "ACTIVE", "snapshot-1", "1", LocalDateTime.now(), null, LocalDateTime.now()));
        when(repository.listCompletedHistory("conversation-1", "dev", 12)).thenReturn(List.of());
        when(pendingCreator.create("conversation-1", "dev", "问题", "request-1", "release-1"))
                .thenReturn(new Pending(run("run-1", null, "PENDING", 0),
                        message("user-1", "USER", "问题"), message("answer-1", "ASSISTANT", ""), true));
        when(ai.submitCustomerServiceMessage(eq("conversation-1"), any())).thenThrow(
                new com.aiep.platformai.agent.AgentTransportException(503, "CS_AGENT_UNAVAILABLE", "智能客服 Agent 当前不可用"));

        assertThatThrownBy(() -> service.submit("dev", "1", "conversation-1", "customer-service-message/1", "问题", "request-1"))
                .isInstanceOf(com.aiep.platformai.agent.AgentTransportException.class);
        verify(repository).completeAssistantMessage("answer-1", "", null, "FAILED");
    }

    @Test
    void storesInternalFactsButKeepsThemOutOfPublicProgress() throws Exception {
        var mapper = new ObjectMapper().findAndRegisterModules();
        var projector = new CustomerServiceEventProjector(repository, mapper);
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 0));
        when(repository.findAssistantMessageByRun("run-1", "dev")).thenReturn(message("answer-1", "ASSISTANT", ""));
        when(repository.advanceRun("run-1", 0, 1, "RUNNING", null, null, null)).thenReturn(true);
        var event = mapper.readValue("""
                {"contract_version":"customer-service-run-event/1","run_id":"agent-run-1","sequence":1,
                 "event_type":"stage.completed","status":"RUNNING","occurred_at":"2026-10-23T00:00:00Z",
                 "payload":{"stage":"retrieval","public_summary":"完成检索","retrieval_facts":{
                 "equivalence_errors":["INTERNAL_ONLY"],"version_exclusions":[],"final_parent_candidates":["frozen-parent"]}}}
                """, CustomerServiceRunEvent.class);
        var result = projector.project("run-1", "dev", event);
        var saved = ArgumentCaptor.forClass(com.aiep.aihub.repository.customer.CustomerServicePOs.RunStepPO.class);
        verify(repository).insertRunStep(saved.capture());
        assertThat(saved.getValue().internalPayload()).contains("INTERNAL_ONLY", "frozen-parent");
        assertThat(mapper.writeValueAsString(result.payload())).doesNotContain("INTERNAL_ONLY", "retrieval_facts", "frozen-parent");
    }

    @Test
    void projectsLiveStageUsingFixedPublicCopy() throws Exception {
        var mapper = new ObjectMapper().findAndRegisterModules();
        var projector = new CustomerServiceEventProjector(repository, mapper);
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 0));
        when(repository.findAssistantMessageByRun("run-1", "dev")).thenReturn(message("answer-1", "ASSISTANT", ""));
        when(repository.advanceRun("run-1", 0, 1, "RUNNING", null, null, null)).thenReturn(true);
        var event = mapper.readValue("""
                {"contract_version":"customer-service-run-event/1","run_id":"agent-run-1","sequence":1,
                 "event_type":"stage.started","status":"RUNNING","occurred_at":"2026-10-26T00:00:00Z",
                 "payload":{"stage":"retrieval","phase":"STARTED","public_summary":"UNTRUSTED CONTENT"}}
                """, CustomerServiceRunEvent.class);
        var result = projector.project("run-1", "dev", event);
        assertThat(result.eventType()).isEqualTo("run.progress");
        assertThat(result.payload()).isEqualTo(java.util.Map.of(
                "stage", "retrieval", "phase", "STARTED", "summary", "正在查找公司资料"));
    }

    @Test
    void timelineExposesOnlyPublicStagesAndConsistentCursor() {
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 3));
        when(repository.findAssistantMessageByRun("run-1", "dev"))
                .thenReturn(message("answer-1", "ASSISTANT", "已生成正文"));
        when(repository.listCitationsByMessage("answer-1")).thenReturn(List.of());
        when(repository.listRunSteps("run-1")).thenReturn(List.of(
                new RunStepPO("step-1", "run-1", 2, "retrieval", "RUNNING", "UNTRUSTED CONTENT",
                        "{\"stage\":\"retrieval\",\"phase\":\"STARTED\",\"private\":\"secret\"}", now, now),
                new RunStepPO("step-2", "run-1", 3, "answer.delta", "RUNNING", null,
                        "{\"delta\":\"内部正文\"}", now, now)));
        var timeline = service.timeline("dev", "1", "run-1");
        assertThat(timeline.lastEventSequence()).isEqualTo(3);
        assertThat(timeline.assistant().message().content()).isEqualTo("已生成正文");
        assertThat(timeline.steps()).hasSize(1);
        assertThat(timeline.steps().getFirst().summary()).isEqualTo("正在查找公司资料");
        assertThat(timeline.toString()).doesNotContain("secret", "内部正文", "UNTRUSTED CONTENT");
        assertThatThrownBy(() -> service.timeline("dev", "another-user", "run-1"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void freezesExcerptMetadataInCitationTableAndPublicEvent() throws Exception {
        var mapper = new ObjectMapper().findAndRegisterModules();
        var projector = new CustomerServiceEventProjector(repository, mapper);
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 0));
        when(repository.findAssistantMessageByRun("run-1", "dev")).thenReturn(message("answer-1", "ASSISTANT", ""));
        when(repository.advanceRun("run-1", 0, 1, "RUNNING", null, null, null)).thenReturn(true);
        var citation = mapper.readValue("""
                {"citation_no":1,"parent_id":"parent","citation_type":"EXTRACTED_SPANS",
                 "original_spans":[{"start_offset":0,"end_offset":2,"content_hash":"hash"}]}
                """, CustomerServiceRunEvent.Citation.class);
        var result = projector.project("run-1", "dev", event(1, "citation.ready", citation));
        var saved = ArgumentCaptor.forClass(com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO.class);
        verify(repository).insertCitation(saved.capture());
        var json = mapper.valueToTree(saved.getValue());
        assertThat(json.path("citationType").asText()).isEqualTo("EXTRACTED_SPANS");
        assertThat(json.path("originalSpans").get(0).path("end_offset").asInt()).isEqualTo(2);
        assertThat(result.payload()).isEqualTo(saved.getValue());
    }

    @Test
    void projectorRejectsDuplicateOrLateEventAndFreezesAcceptedCitation() {
        CustomerServiceEventProjector projector = new CustomerServiceEventProjector(repository, new ObjectMapper().findAndRegisterModules());
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 0));
        when(repository.findAssistantMessageByRun("run-1", "dev")).thenReturn(message("answer-1", "ASSISTANT", ""));
        when(repository.advanceRun("run-1", 0, 1, "RUNNING", null, null, null)).thenReturn(true);
        CustomerServiceRunEvent first = event(1, "run.started", null);
        assertThat(projector.project("run-1", "dev", first).eventType()).isEqualTo("run.started");
        when(repository.advanceRun("run-1", 0, 1, "RUNNING", null, null, null)).thenReturn(false);
        when(repository.findRun("run-1", "dev")).thenReturn(run("run-1", "agent-run-1", "RUNNING", 1));
        assertThat(projector.project("run-1", "dev", first).eventType()).isEqualTo("run.started");
        verify(repository).insertRunStep(any());
    }

    private MessagePO message(String id, String role, String content) {
        return new MessagePO(id, "conversation-1", "dev", role, content, "COMPLETED", null, "run-1", null, now);
    }
    private RunPO run(String id, String agentRunId, String status, long sequence) {
        return new RunPO(id, "conversation-1", "dev", "user-1", agentRunId, "release-1", status, null,
                sequence, null, null, now, null, now, now);
    }
    private CustomerServiceRunEvent event(long sequence, String type, CustomerServiceRunEvent.Citation citation) {
        return new CustomerServiceRunEvent("customer-service-run-event/1", "agent-run-1", sequence, type,
                CustomerServiceRunView.Status.RUNNING, now,
                new CustomerServiceRunEvent.Payload("intent", 10, "处理中", null, null, citation, null, null, null));
    }
}
