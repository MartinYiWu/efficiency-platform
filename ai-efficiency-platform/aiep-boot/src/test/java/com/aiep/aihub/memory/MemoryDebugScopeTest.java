package com.aiep.aihub.memory;

import com.aiep.aihub.application.management.AiRagDebugService;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryDebugScopeTest {
    @Test
    void taskOnlyDebugUsesInternalChannelAndWeakSecretCannotSend() throws Exception {
        var bearer = new java.util.concurrent.atomic.AtomicReference<String>();
        var tenant = new java.util.concurrent.atomic.AtomicReference<String>();
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var server = com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            try {
                calls.incrementAndGet();
                bearer.set(exchange.getRequestHeaders().getFirst("Authorization"));
                tenant.set(exchange.getRequestHeaders().getFirst("X-Tenant-ID"));
                exchange.getRequestBody().readAllBytes();
                byte[] response = "{\"contract_version\":\"customer-service-rag-debug-view/1\",\"debug_run_id\":\"debug\",\"status\":\"SUCCEEDED\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, response.length);
                exchange.getResponseBody().write(response);
            } finally { exchange.close(); }
        });
        server.start();
        try {
            var properties = new com.aiep.platformai.agent.AgentClientProperties();
            properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
            String secret = "memory-debug-synthetic-internal-secret";
            properties.setInternalSecret(secret);
            var scope = new com.aiep.platformai.api.dto.MemoryContextEnvelope.Scope("tenant", "user", "customer-service", "customer-service", "TASK_ONLY", null);
            var envelope = new com.aiep.platformai.api.dto.MemoryContextEnvelope("memory-context/1", "DISABLED", scope, null);
            var request = new com.aiep.platformai.api.dto.CustomerServiceDebugRequest("customer-service-rag-debug/1", "customer-service", "tenant", "合成问题", "release", "version", "rag", List.of(), envelope);
            new com.aiep.platformai.agent.HttpCustomerServiceAgentClient(properties, org.springframework.web.reactive.function.client.WebClient.builder(), new ObjectMapper()).runDebug(request);
            assertEquals("Bearer " + secret, bearer.get());
            assertEquals("tenant", tenant.get());
            properties.setInternalSecret("");
            var missing = new com.aiep.platformai.agent.HttpCustomerServiceAgentClient(properties, org.springframework.web.reactive.function.client.WebClient.builder(), new ObjectMapper());
            var error = assertThrows(com.aiep.platformai.agent.AgentTransportException.class, () -> missing.runDebug(request));
            assertEquals("MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED", error.getErrorCode());
            assertEquals(1, calls.get());
        } finally { server.stop(0); }
    }

    @Test
    void legacyConstructorDoesNotInventDebugIdentityOrReadRepository() {
        var repository = mock(AiManagementMappers.class);
        var ai = mock(AiInvokeFacade.class);
        var jdbc = mock(JdbcTemplate.class);
        var service = new AiRagDebugService(repository, ai, jdbc, new ObjectMapper());
        var request = new AiRagDebugService.Request("customer-service", "合成问题", "v", "rag", List.of());
        var error = assertThrows(IllegalStateException.class, () -> service.execute(request));
        assertEquals("MEMORY_IDENTITY_REQUIRED", error.getMessage());
        verifyNoInteractions(repository, ai, jdbc);
    }

    @Test
    void unauthenticatedReadCannotQueryStoredDebugBody() {
        var repository = mock(AiManagementMappers.class);
        var ai = mock(AiInvokeFacade.class);
        var jdbc = mock(JdbcTemplate.class);
        var service = new AiRagDebugService(repository, ai, jdbc, new ObjectMapper());
        var error = assertThrows(IllegalStateException.class, () -> service.get("run"));
        assertEquals("MEMORY_IDENTITY_REQUIRED", error.getMessage());
        verifyNoInteractions(repository, ai, jdbc);
    }
}
