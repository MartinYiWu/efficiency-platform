package com.aiep.aihub.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector;
import com.aiep.aihub.application.customer.CustomerServicePendingRunCreator;
import com.aiep.aihub.repository.customer.CustomerServiceMappers;
import com.aiep.aihub.repository.customer.CustomerServicePOs.*;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO;
import com.aiep.aihub.repository.management.AiReleasePO;
import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.HttpCustomerServiceAgentClient;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.web.reactive.function.client.WebClient;

/** 仅本机合成上游；Java 仓储为 Mockito 状态存根，不代表真实数据库验收。 */
class CustomerServicePaidBudgetChainTest {
    private static final ObjectMapper JSON = new ObjectMapper().findAndRegisterModules();
    private static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    private static final String RELEASE = "00000000-0000-0000-0000-000000000001";
    private static Process fixture;
    private static String baseUrl;
    private static Path evidence;

    @BeforeAll
    static void startFixture() throws Exception {
        Path root = Path.of(System.getProperty("user.dir")).toAbsolutePath();
        while (root != null && !Files.isDirectory(root.resolve("efficiency-platform-agent"))) root = root.getParent();
        assertThat(root).as("workspace root").isNotNull();
        evidence = root.resolve(".local-acceptance/business-budget-20261103");
        Files.createDirectories(evidence);
        Path agent = root.resolve("efficiency-platform-agent");
        Path work = Files.createTempDirectory("aiep-paid-chain-");
        int port;
        try (ServerSocket socket = new ServerSocket(0, 0, java.net.InetAddress.getLoopbackAddress())) {
            port = socket.getLocalPort();
        }
        baseUrl = "http://127.0.0.1:" + port;
        ProcessBuilder builder = new ProcessBuilder(agent.resolve(".venv/Scripts/python.exe").toString(),
                "tests/integration/paid_budget_agent_fixture.py", "--port", Integer.toString(port), "--workdir", work.toString());
        builder.directory(agent.toFile()).redirectErrorStream(true)
                .redirectOutput(evidence.resolve("java-chain-fixture.log").toFile());
        builder.environment().keySet().removeIf(key -> key.contains("API_KEY") || key.contains("TOKEN")
                || key.equals("OPENAI_BASE_URL") || key.equals("DATABASE_URL"));
        fixture = builder.start();
        try {
            long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
            while (System.nanoTime() < deadline && fixture.isAlive()) {
                try {
                    if (HTTP.send(HttpRequest.newBuilder(URI.create(baseUrl + "/health/ready"))
                            .timeout(Duration.ofSeconds(1)).build(), HttpResponse.BodyHandlers.discarding()).statusCode() == 200) return;
                } catch (java.io.IOException ignored) { }
                Thread.sleep(100);
            }
            throw new AssertionError("Local fixture did not become ready; see java-chain-fixture.log");
        } catch (Throwable failure) {
            stopFixture();
            throw failure;
        }
    }

    @AfterAll
    static void stopFixture() throws Exception {
        if (fixture == null) return;
        fixture.destroy();
        if (!fixture.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)) {
            fixture.destroyForcibly();
            assertThat(fixture.waitFor(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
        }
        assertThat(fixture.isAlive()).isFalse();
        Files.writeString(evidence.resolve("java-chain-cleanup.txt"), "fixture_pid=" + fixture.pid()
                + "\nalive=false\nbase_url=" + baseUrl + "\n");
    }

    @Test
    void successProjectsCompletionAndDuplicateClientRequestDoesNotDispatch() throws Exception {
        Harness harness = new Harness("success");
        harness.submit();
        harness.collect();
        assertThat(harness.run.status()).isEqualTo("SUCCEEDED");
        assertThat(harness.answer.status()).isEqualTo("COMPLETED");
        assertThat(harness.answer.content()).isNotBlank();
        assertThat(harness.publicEvents).extracting(CustomerServiceEventProjector.PublicEvent::eventType).contains("run.completed");
        int before = observation("success").path("upstream_requests").asInt();
        assertThat(before).isEqualTo(2);
        JsonNode success = observation("success").path("snapshot");
        assertThat(success.path("calls").asInt()).isEqualTo(2);
        assertThat(success.path("cost_microunits").asInt()).isEqualTo(2);
        assertThat(success.at("/accounting/actual_tokens/input_tokens").asInt()).isEqualTo(20);
        assertThat(success.at("/accounting/actual_tokens/output_tokens").asInt()).isEqualTo(10);
        assertThat(success.at("/accounting/held_cost_microunits").asInt()).isZero();
        assertThat(harness.submit().runId()).isEqualTo(harness.id);
        assertThat(observation("success").path("upstream_requests").asInt()).isEqualTo(before);
        verify(harness.ai, times(1)).submitCustomerServiceMessage(anyString(), any());
        harness.assertPublicSafe();
    }

    @ParameterizedTest
    @ValueSource(strings = {"exhaust", "tokens", "money"})
    void budgetRefusalProjectsFailedAssistantWithoutSecondUpstreamDispatch(String scenario) throws Exception {
        Harness harness = new Harness(scenario);
        harness.submit();
        harness.collect();
        assertThat(harness.run.status()).isEqualTo("FAILED");
        assertThat(harness.run.failureCode()).isIn("RUN_EXHAUSTED", "BUDGET_EXHAUSTED");
        assertThat(harness.answer.status()).isEqualTo("FAILED");
        assertThat(harness.publicEvents).extracting(CustomerServiceEventProjector.PublicEvent::eventType)
                .contains("run.failed").doesNotContain("run.completed");
        assertThat(observation(scenario).path("upstream_requests").asInt()).isEqualTo(1);
        harness.assertPublicSafe();
    }

    @Test
    void missingAuthorizationProjectsFailureWithoutAnyUpstreamRequest() throws Exception {
        Harness harness = new Harness("unauthorized");
        harness.submit();
        harness.collect();
        assertThat(harness.run.status()).isEqualTo("FAILED");
        assertThat(harness.run.failureCode()).isEqualTo("NO_BUDGET");
        assertThat(harness.answer.status()).isEqualTo("FAILED");
        assertThat(harness.publicEvents).extracting(CustomerServiceEventProjector.PublicEvent::eventType)
                .contains("run.failed").doesNotContain("run.completed");
        assertThat(observation("unauthorized").path("upstream_requests").asInt()).isZero();
        assertThat(observation("unauthorized").path("snapshot").isEmpty()).isTrue();
        harness.assertPublicSafe();
    }

    @Test
    void retryConsumesAnAdditionalRealLocalHttpAttempt() throws Exception {
        Harness harness = new Harness("retry");
        harness.submit();
        harness.collect();
        assertThat(harness.run.status()).isEqualTo("SUCCEEDED");
        assertThat(observation("retry").path("upstream_requests").asInt()).isEqualTo(3);
        JsonNode retry = observation("retry").path("snapshot");
        assertThat(retry.path("calls").asInt()).isEqualTo(3);
        assertThat(retry.path("cost_microunits").asInt()).isEqualTo(12);
        assertThat(retry.at("/accounting/actual_cost_microunits").asInt()).isEqualTo(2);
        assertThat(retry.at("/accounting/held_cost_microunits").asInt()).isEqualTo(10);
        harness.assertPublicSafe();
    }

    @Test
    void cancellationReachesPythonAndProjectsCancelledAssistant() throws Exception {
        Harness harness = new Harness("cancel");
        harness.submit();
        long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
        while (observation("cancel").path("upstream_requests").asInt() < 2 && System.nanoTime() < deadline) Thread.sleep(50);
        assertThat(observation("cancel").path("upstream_requests").asInt()).isEqualTo(2);
        harness.service.cancel("dev", harness.id);
        harness.collect();
        assertThat(harness.run.status()).isEqualTo("CANCELLED");
        assertThat(harness.answer.status()).isEqualTo("CANCELLED");
        assertThat(harness.publicEvents).extracting(CustomerServiceEventProjector.PublicEvent::eventType).contains("run.cancelled");
        JsonNode cancelled = observation("cancel").path("snapshot");
        assertThat(cancelled.at("/accounting/unknown_attempts").asInt()).isEqualTo(1);
        assertThat(cancelled.at("/accounting/held_cost_microunits").asInt()).isEqualTo(10);
        harness.assertPublicSafe();
    }

    @Test
    void concurrentQuestionsShareThreeAttemptLimit() throws Exception {
        Harness first = new Harness("concurrent");
        Harness second = new Harness("concurrent");
        CompletableFuture<Void> left = CompletableFuture.runAsync(() -> { first.submit(); first.collect(); });
        CompletableFuture<Void> right = CompletableFuture.runAsync(() -> { second.submit(); second.collect(); });
        CompletableFuture.allOf(left, right).get(30, java.util.concurrent.TimeUnit.SECONDS);
        assertThat(List.of(first.run.status(), second.run.status())).contains("FAILED");
        assertThat(observation("concurrent").path("upstream_requests").asInt()).isLessThanOrEqualTo(3);
        first.assertPublicSafe();
        second.assertPublicSafe();
    }

    private static JsonNode observation(String scenario) throws Exception {
        HttpResponse<String> response = HTTP.send(HttpRequest.newBuilder(URI.create(baseUrl + "/test/observations/" + scenario))
                .timeout(Duration.ofSeconds(3)).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        JsonNode result = JSON.readTree(response.body());
        Files.writeString(evidence.resolve("java-chain-observation-" + scenario + ".json"),
                JSON.writerWithDefaultPrettyPrinter().writeValueAsString(result));
        return result;
    }

    private static final class Harness {
        final String id = UUID.randomUUID().toString();
        final String requestId = UUID.randomUUID().toString();
        final Instant now = Instant.now();
        final CustomerServiceMappers repository = mock(CustomerServiceMappers.class);
        final AiInvokeFacade ai = mock(AiInvokeFacade.class);
        final CustomerServiceApplicationService service;
        final CustomerServiceEventProjector projector = new CustomerServiceEventProjector(repository, JSON);
        final List<CustomerServiceEventProjector.PublicEvent> publicEvents = new ArrayList<>();
        final List<RunStepPO> steps = new ArrayList<>();
        RunPO run;
        MessagePO answer;
        MessagePO question;

        Harness(String scenario) {
            var properties = new AgentClientProperties();
            properties.setBaseUrl(baseUrl + "/" + scenario);
            properties.setInternalSecret("paid-chain-synthetic-internal-secret-000");
            properties.setCustomerServiceStreamIdleTimeout(Duration.ofSeconds(20));
            var client = new HttpCustomerServiceAgentClient(properties, WebClient.builder(), JSON);
            when(ai.submitCustomerServiceMessage(anyString(), any())).thenAnswer(call -> client.submitMessage(call.getArgument(0), call.getArgument(1)));
            when(ai.streamCustomerServiceRunEvents(anyString(), anyLong())).thenAnswer(call -> client.streamRun(call.getArgument(0), call.getArgument(1)));
            when(ai.cancelCustomerServiceRun(anyString())).thenAnswer(call -> client.cancelRun(call.getArgument(0)));
            var management = mock(AiManagementMappers.class);
            when(management.findAgentByKey("customer-service")).thenReturn(new AgentDefinitionPO("agent", "customer-service", "客服", "", "CUSTOMER_SERVICE", "ACTIVE", "1", null, "1", null));
            when(management.findActiveRelease("agent", "dev")).thenReturn(new AiReleasePO(RELEASE, "agent", "version", "dev", "ACTIVE", "snapshot", "1", LocalDateTime.now(), null, LocalDateTime.now()));
            when(repository.findConversation("00000000-0000-0000-0000-000000000002", "dev", "1")).thenReturn(new ConversationPO("00000000-0000-0000-0000-000000000002", "dev", "1", "测试", "ACTIVE", now, now, now));
            when(repository.listCompletedHistory(anyString(), anyString(), anyInt())).thenReturn(List.of());
            when(repository.findMessageByClientRequest("dev", requestId)).thenAnswer(call -> question);
            when(repository.findRunByUserMessage(anyString(), eq("dev"))).thenAnswer(call -> run);
            when(repository.findRun(id, "dev")).thenAnswer(call -> run);
            when(repository.findAssistantMessageByRun(id, "dev")).thenAnswer(call -> answer);
            when(repository.listRunSteps(id)).thenAnswer(call -> List.copyOf(steps));
            when(repository.listCitationsByMessage(anyString())).thenReturn(List.of());
            doAnswer(call -> { run = updatedRun(call.getArgument(1), call.getArgument(2), run.lastEventSequence(), null, null, null); return null; })
                    .when(repository).bindAgentRun(eq(id), anyString(), anyString());
            when(repository.advanceRun(eq(id), anyLong(), anyLong(), anyString(), nullable(String.class), nullable(String.class), nullable(String.class)))
                    .thenAnswer(call -> {
                        if (run.lastEventSequence() != (long) call.getArgument(1)) return false;
                        run = updatedRun(run.agentRunId(), call.getArgument(3), call.getArgument(2), call.getArgument(4), call.getArgument(5), call.getArgument(6));
                        return true;
                    });
            doAnswer(call -> { steps.add(call.getArgument(0)); return null; }).when(repository).insertRunStep(any());
            doAnswer(call -> { answer = message("answer", "ASSISTANT", call.getArgument(1), call.getArgument(3), call.getArgument(2)); return null; })
                    .when(repository).completeAssistantMessage(anyString(), anyString(), nullable(String.class), anyString());
            var pending = mock(CustomerServicePendingRunCreator.class);
            when(pending.create(anyString(), anyString(), anyString(), anyString(), eq(RELEASE))).thenAnswer(call -> {
                run = new RunPO(id, "00000000-0000-0000-0000-000000000002", "dev", "question", null, RELEASE, "PENDING", null, 0, null, null, now, null, now, now);
                question = message("question", "USER", "测试问题", "COMPLETED", null);
                answer = message("answer", "ASSISTANT", "", "PENDING", null);
                return new CustomerServicePendingRunCreator.Pending(run, question, answer, true);
            });
            service = new CustomerServiceApplicationService(repository, management, pending, ai);
        }

        com.aiep.aihub.application.customer.CustomerServiceViews.SubmitView submit() {
            return service.submit("dev", "1", "00000000-0000-0000-0000-000000000002", "customer-service-message/1", "测试问题", requestId);
        }

        void collect() {
            service.stream("dev", id, 0).doOnNext(event -> {
                var projected = projector.project(id, "dev", event);
                if (projected != null) publicEvents.add(projected);
            }).blockLast(Duration.ofSeconds(25));
        }

        void assertPublicSafe() throws Exception {
            assertThat(JSON.writeValueAsString(publicEvents)).doesNotContain("retrieval_facts", "budget_usage", "ledger", "input_tokens", "output_tokens", "system_prompt", "api_key");
            assertThat(projector.replay(id, "dev", 0)).isNotEmpty();
            assertThat(service.timeline("dev", "1", id).assistant().message().status()).isEqualTo(answer.status());
        }

        private MessagePO message(String messageId, String role, String content, String status, String mode) {
            return new MessagePO(messageId, "00000000-0000-0000-0000-000000000002", "dev", role, content, status, mode, id, requestId, now);
        }

        private RunPO updatedRun(String agentRunId, String status, long sequence, String mode, String code, String error) {
            return new RunPO(id, "00000000-0000-0000-0000-000000000002", "dev", "question", agentRunId, RELEASE, status, mode, sequence, code, error, now, null, now, now);
        }
    }
}
