package com.aiep.platformai;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.aiep.platformai.agent.AgentClientProperties;
import com.aiep.platformai.agent.AgentEndpoints;
import com.aiep.platformai.agent.AgentTransportException;
import com.aiep.platformai.agent.HttpCustomerServiceAgentClient;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunView;
import com.aiep.platformai.api.dto.CustomerServiceDebugRequest;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class CustomerServiceAgentContractTest {

    private final ObjectMapper objectMapper = new ObjectMapper()
            .findAndRegisterModules()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    @Test
    void exposesDedicatedCustomerServiceEndpoints() {
        assertEquals("/internal/v1/customer-service/releases/{release_id}", AgentEndpoints.CUSTOMER_SERVICE_RELEASE);
        assertEquals("/internal/v1/customer-service/ingest-jobs", AgentEndpoints.CUSTOMER_SERVICE_INGEST_JOBS);
        assertEquals("/v1/customer-service/runs/{run_id}/events", AgentEndpoints.CUSTOMER_SERVICE_RUN_EVENTS);
        assertEquals("/internal/v1/customer-service/rag-debug-runs", AgentEndpoints.CUSTOMER_SERVICE_RAG_DEBUG);
    }

    @Test
    void rejectsHistoryOutsideThePublishedContract() {
        List<CustomerServiceRunRequest.HistoryMessage> history = new ArrayList<>();
        for (int index = 0; index < 13; index++) {
            history.add(new CustomerServiceRunRequest.HistoryMessage("user", "消息" + index));
        }

        assertThrows(IllegalArgumentException.class, () -> new CustomerServiceRunRequest(
                "customer-service-run/1",
                "request-1",
                "conversation-1",
                "dev",
                "1",
                "release-1",
                "问题",
                history));
    }

    @Test
    void rejectsUnknownResponseFields() {
        String payload = """
                {
                  "contract_version": "customer-service-run-view/1",
                  "run_id": "run-1",
                  "request_id": "request-1",
                  "status": "RUNNING",
                  "unexpected": true
                }
                """;

        assertThrows(Exception.class, () -> objectMapper.readValue(payload, CustomerServiceRunView.class));
    }

    @Test
    void ragDebugContractCarriesTenantBoundary() throws Exception {
        CustomerServiceDebugRequest request = new CustomerServiceDebugRequest(
                "customer-service-rag-debug/1", "customer-service", "dev", "发布流程是什么？",
                "release-1", "version-1", "rag-1",
                List.of(new CustomerServiceDebugRequest.KnowledgeBinding("kb-1", "index-1")));

        String json = objectMapper.writeValueAsString(request);

        assertEquals("dev", objectMapper.readTree(json).get("tenant_id").asText());
    }

    @Test
    void decodesSseInSequenceAndAddsTraceHeader() {
        String body = """
                data: {"contract_version":"customer-service-run-event/1","run_id":"run-1","sequence":1,"event_type":"run.started","status":"RUNNING","occurred_at":"2026-10-20T06:00:00Z","payload":{"stage":"intent"}}

                data: {"contract_version":"customer-service-run-event/1","run_id":"run-1","sequence":2,"event_type":"answer.completed","status":"SUCCEEDED","occurred_at":"2026-10-20T06:00:01Z","payload":{"answer_mode":"COMPANY_KNOWLEDGE"}}

                """;
        AtomicReference<ClientRequest> captured = new AtomicReference<>();
        ExchangeFunction exchange = request -> {
            captured.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_EVENT_STREAM_VALUE)
                    .body(body)
                    .build());
        };
        HttpCustomerServiceAgentClient client = createClient(exchange);

        List<CustomerServiceRunEvent> events = client.streamRun("run-1", 0).collectList().block();

        assertNotNull(events);
        assertEquals(List.of(1L, 2L), events.stream().map(CustomerServiceRunEvent::sequence).toList());
        assertNotNull(captured.get().headers().getFirst("X-Trace-Id"));
    }

    @Test
    void mapsDownstreamServerFailureWithoutInventingSuccess() {
        ExchangeFunction exchange = request -> Mono.just(ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body("{\"detail\":\"unavailable\"}")
                .build());
        HttpCustomerServiceAgentClient client = createClient(exchange);

        AgentTransportException exception = assertThrows(
                AgentTransportException.class,
                () -> client.cancelRun("run-1"));

        assertEquals("CS_AGENT_UNAVAILABLE", exception.getErrorCode());
    }

    @Test
    void preservesUnavailableCauseAfterConnectionRetryIsExhausted() {
        ExchangeFunction exchange = request -> Mono.error(
                new org.springframework.web.reactive.function.client.WebClientRequestException(
                        new java.net.ConnectException("controlled unavailable"),
                        request.method(), request.url(), request.headers()));
        AgentTransportException error = assertThrows(AgentTransportException.class,
                () -> createClient(exchange).cancelRun("unavailable-run"));
        assertEquals(503, error.getStatusCode());
        assertEquals("CS_AGENT_UNAVAILABLE", error.getErrorCode());
    }

    private HttpCustomerServiceAgentClient createClient(ExchangeFunction exchangeFunction) {
        AgentClientProperties properties = new AgentClientProperties();
        properties.setBaseUrl("http://agent.invalid");
        properties.setCustomerServiceResponseTimeout(Duration.ofSeconds(5));
        properties.setCustomerServiceStreamIdleTimeout(Duration.ofSeconds(5));
        return new HttpCustomerServiceAgentClient(
                properties,
                WebClient.builder().exchangeFunction(exchangeFunction),
                objectMapper);
    }
}
