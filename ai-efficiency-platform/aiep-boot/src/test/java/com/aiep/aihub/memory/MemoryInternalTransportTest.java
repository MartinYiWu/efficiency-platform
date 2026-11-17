package com.aiep.aihub.memory;

import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.AgentTransportException;
import com.aiep.platformai.agent.HttpAgentClient;
import com.aiep.platformai.agent.HttpCustomerServiceAgentClient;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.MemoryContextEnvelope;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.web.reactive.function.client.WebClient;
import static org.junit.jupiter.api.Assertions.*;

/** 本机JDK合成接收端，只验证HTTP协议，不启动真实Agent或供应商。 */
class MemoryInternalTransportTest {
    private static final String SYNTHETIC_SECRET = "synthetic-context-transport-only-000000000000";
    private final ObjectMapper json = new ObjectMapper();
    private final AtomicInteger received = new AtomicInteger();
    private final AtomicReference<String> authorization = new AtomicReference<>();
    private final AtomicReference<String> tenant = new AtomicReference<>();
    private final AtomicReference<String> body = new AtomicReference<>();
    private HttpServer server;

    @BeforeEach
    void startSyntheticReceiver() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            try {
                received.incrementAndGet();
                authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
                tenant.set(exchange.getRequestHeaders().getFirst("X-Tenant-ID"));
                body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                boolean customer = exchange.getRequestURI().getPath().contains("customer-service");
                byte[] response = (customer
                        ? "{\"contract_version\":\"customer-service-run-view/1\",\"run_id\":\"agent-run\",\"request_id\":\"request\",\"status\":\"PENDING\"}"
                        : "{\"contract_version\":\"operation-run/1\",\"conversation_id\":\"session\",\"turn_id\":\"turn\",\"run_id\":\"agent-run\",\"status\":\"queued\"}")
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, response.length);
                exchange.getResponseBody().write(response);
            } finally {
                exchange.close();
            }
        });
        server.start();
    }

    @AfterEach
    void stopSyntheticReceiver() {
        server.stop(0);
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void scopedEnvelopeSendsInternalBearerTenantAndSnakeCaseScope(boolean customer) throws Exception {
        submit(customer, SYNTHETIC_SECRET, true);
        assertEquals(1, received.get());
        assertTrue(("Bearer " + SYNTHETIC_SECRET).equals(authorization.get()), "内部Bearer必须匹配配置");
        assertEquals("tenant", tenant.get());
        assertFalse(body.get().contains(SYNTHETIC_SECRET));
        JsonNode envelope = json.readTree(body.get()).path("memory_context");
        assertEquals("memory-context/1", envelope.path("schema_version").asText());
        assertEquals("DISABLED", envelope.path("memory_mode").asText());
        assertTrue(envelope.path("packet").isNull());
        assertEquals(6, envelope.path("scope").size());
        assertEquals("tenant", envelope.at("/scope/tenant_id").asText());
        assertEquals("user", envelope.at("/scope/user_id").asText());
        assertEquals(customer ? "customer-service" : "operations", envelope.at("/scope/top_level_agent_id").asText());
        assertEquals("session", envelope.at("/scope/session_id").asText());
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void scopedEnvelopeRejectsMissingWeakSecretBeforeAnyHttp(boolean customer) {
        for (String secret : new String[] {null, "", "short", "x".repeat(31), " ".repeat(32)}) {
            AgentTransportException error = assertThrows(AgentTransportException.class,
                    () -> submit(customer, secret, true));
            assertEquals("MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED", error.getErrorCode());
            assertEquals(503, error.getStatusCode());
        }
        assertEquals(0, received.get());
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    void legacyDisabledNullScopeRemainsCompatibleWithoutInternalSecret(boolean customer) throws Exception {
        submit(customer, "", false);
        assertEquals(1, received.get());
        assertNull(authorization.get());
        JsonNode envelope = json.readTree(body.get()).path("memory_context");
        assertEquals("DISABLED", envelope.path("memory_mode").asText());
        assertTrue(envelope.path("scope").isNull());
    }

    private void submit(boolean customer, String secret, boolean scoped) {
        AgentClientProperties properties = new AgentClientProperties();
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setResponseTimeout(Duration.ofSeconds(3));
        properties.setCustomerServiceResponseTimeout(Duration.ofSeconds(3));
        properties.setInternalSecret(secret);
        String agent = customer ? "customer-service" : "operations";
        MemoryContextEnvelope envelope = scoped
                ? new MemoryContextEnvelope("memory-context/1", "DISABLED",
                        new MemoryContextEnvelope.Scope("tenant", "user", agent, agent, "CONVERSATION", "session"), null)
                : MemoryContextEnvelope.disabled();
        if (customer) {
            new HttpCustomerServiceAgentClient(properties, WebClient.builder(), json).submitMessage("session",
                    new CustomerServiceRunRequest("customer-service-run/1", "request", "session", "tenant", "user",
                            "release", "synthetic message", List.of(), envelope));
        } else {
            new HttpAgentClient(properties, WebClient.builder(), json).submitOperationMessage("session",
                    new OperationAgentMessageRequest("synthetic message", "request", "user", List.of(), "tenant", envelope));
        }
    }
}
