package com.aiep.platformai.agent;

import com.aiep.platformai.api.dto.CustomerServiceDebugRequest;
import com.aiep.platformai.api.dto.CustomerServiceDebugView;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyView;
import com.aiep.platformai.api.dto.CustomerServiceIndexVerifyRequest;
import com.aiep.platformai.api.dto.CustomerServiceIngestRequest;
import com.aiep.platformai.api.dto.CustomerServiceIngestView;
import com.aiep.platformai.api.dto.CustomerServiceReleaseAck;
import com.aiep.platformai.api.dto.CustomerServiceReleaseRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunEvent;
import com.aiep.platformai.api.dto.CustomerServiceRunRequest;
import com.aiep.platformai.api.dto.CustomerServiceRunView;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.netty.channel.ChannelOption;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;
import reactor.util.retry.Retry;

/** 独立智能客服 Agent 的 HTTP/SSE 适配器。 */
@Component
public final class HttpCustomerServiceAgentClient implements CustomerServiceAgentClient {
    private static final Logger log = LoggerFactory.getLogger(HttpCustomerServiceAgentClient.class);
    private static final String TRACE_HEADER = "X-Trace-Id";
    private static final ParameterizedTypeReference<ServerSentEvent<String>> EVENT_TYPE =
            new ParameterizedTypeReference<>() { };

    private final WebClient webClient;
    private final ObjectMapper objectMapper;
    private final Duration streamIdleTimeout;

    public HttpCustomerServiceAgentClient(
            AgentClientProperties properties,
            WebClient.Builder builder,
            ObjectMapper objectMapper) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        Math.toIntExact(properties.getConnectTimeout().toMillis()))
                .responseTimeout(properties.getCustomerServiceResponseTimeout());
        this.webClient = builder
                .baseUrl(properties.getBaseUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
        this.objectMapper = objectMapper.copy()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        this.streamIdleTimeout = properties.getCustomerServiceStreamIdleTimeout();
    }

    @Override
    public CustomerServiceReleaseAck publishRelease(
            String releaseId, CustomerServiceReleaseRequest request) {
        return exchange(webClient.put()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_RELEASE, releaseId)
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request), CustomerServiceReleaseAck.class, "release_publish", releaseId);
    }

    @Override
    public CustomerServiceIngestView submitIngest(CustomerServiceIngestRequest request) {
        return exchange(webClient.post()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_INGEST_JOBS)
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request), CustomerServiceIngestView.class, "ingest_submit", request.taskId());
    }

    @Override
    public CustomerServiceIngestView getIngest(String taskId) {
        return exchange(webClient.get()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_INGEST_JOB, taskId)
                .header(TRACE_HEADER, traceId()), CustomerServiceIngestView.class, "ingest_query", taskId);
    }

    @Override
    public CustomerServiceIndexVerifyView verifyIndex(CustomerServiceIndexVerifyRequest request) {
        return exchange(webClient.post()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_INDEX_VERIFY, request.releaseId())
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request), CustomerServiceIndexVerifyView.class,
                "index_verify", request.releaseId());
    }

    @Override
    public CustomerServiceRunView submitMessage(
            String conversationId, CustomerServiceRunRequest request) {
        return exchange(webClient.post()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_MESSAGES, conversationId)
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request), CustomerServiceRunView.class, "message_submit", request.requestId());
    }

    @Override
    public Flux<CustomerServiceRunEvent> streamRun(String runId, long afterSequence) {
        WebClient.RequestHeadersSpec<?> request = webClient.get()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_RUN_EVENTS, runId)
                .header(TRACE_HEADER, traceId())
                .accept(MediaType.TEXT_EVENT_STREAM);
        if (afterSequence > 0) {
            request = request.header("Last-Event-ID", Long.toString(afterSequence));
        }
        AtomicLong lastSequence = new AtomicLong(afterSequence);
        log.info("event=customer_service_sse_connecting agentRunId={} afterSequence={}", runId, afterSequence);
        return request.retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToFlux(EVENT_TYPE)
                .filter(event -> event.data() != null)
                .map(event -> decode(Objects.requireNonNull(event.data()), CustomerServiceRunEvent.class))
                .map(event -> requireSequence(runId, lastSequence, event))
                .timeout(streamIdleTimeout)
                .doOnNext(event -> log.info(
                        "event=customer_service_sse_event agentRunId={} sequence={} type={} status={}",
                        runId, event.sequence(), event.eventType(), event.status()))
                .doOnComplete(() -> log.info("event=customer_service_sse_completed agentRunId={}", runId))
                .doOnError(error -> log.error(
                        "event=customer_service_sse_failed agentRunId={} errorType={}",
                        runId, error.getClass().getSimpleName()))
                .onErrorMap(WebClientRequestException.class, ignored -> unavailable());
    }

    @Override
    public CustomerServiceRunView cancelRun(String runId) {
        return exchange(webClient.post()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_RUN_CANCEL, runId)
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CancelRequest("customer-service-cancel/1", "user_requested")),
                CustomerServiceRunView.class, "run_cancel", runId);
    }

    @Override
    public CustomerServiceDebugView runDebug(CustomerServiceDebugRequest request) {
        return exchange(webClient.post()
                .uri(AgentEndpoints.CUSTOMER_SERVICE_RAG_DEBUG)
                .header(TRACE_HEADER, traceId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request), CustomerServiceDebugView.class, "rag_debug", request.agentVersionId());
    }

    private <T> T exchange(
            WebClient.RequestHeadersSpec<?> request,
            Class<T> responseType,
            String operation,
            String resourceId) {
        long startedAt = System.nanoTime();
        try {
            String body = request.retrieve()
                    .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                    .bodyToMono(String.class)
                    .retryWhen(Retry.max(1).filter(WebClientRequestException.class::isInstance)
                            .onRetryExhaustedThrow((spec, signal) -> signal.failure()))
                    .onErrorMap(WebClientRequestException.class, ignored -> unavailable())
                    .block();
            if (body == null || body.isBlank()) {
                throw new AgentTransportException(502, "CS_AGENT_EMPTY_RESPONSE", "智能客服 Agent 返回空响应");
            }
            T result = decode(body, responseType);
            log.info("event=customer_service_agent_succeeded operation={} resourceId={} elapsedMs={}",
                    operation, resourceId, elapsedMillis(startedAt));
            return result;
        } catch (AgentTransportException exception) {
            log.error("event=customer_service_agent_failed operation={} resourceId={} errorCode={} elapsedMs={}",
                    operation, resourceId, exception.getErrorCode(), elapsedMillis(startedAt));
            throw exception;
        }
    }

    private <T> T decode(String body, Class<T> responseType) {
        try {
            return objectMapper.readValue(body, responseType);
        } catch (JsonProcessingException | IllegalArgumentException exception) {
            throw new AgentTransportException(502, "CS_AGENT_CONTRACT_INVALID", "智能客服 Agent 响应契约无效");
        }
    }

    private static CustomerServiceRunEvent requireSequence(
            String runId, AtomicLong lastSequence, CustomerServiceRunEvent event) {
        if (!runId.equals(event.runId()) || event.sequence() <= lastSequence.get()) {
            throw new AgentTransportException(502, "CS_AGENT_EVENT_SEQUENCE_INVALID", "智能客服事件序号无效");
        }
        lastSequence.set(event.sequence());
        return event;
    }

    private static Mono<? extends Throwable> downstreamError(int statusCode) {
        String errorCode = statusCode >= 500 ? "CS_AGENT_UNAVAILABLE" : "CS_AGENT_REJECTED";
        return Mono.just(new AgentTransportException(statusCode, errorCode, "智能客服 Agent 请求失败"));
    }

    private static AgentTransportException unavailable() {
        return new AgentTransportException(503, "CS_AGENT_UNAVAILABLE", "智能客服 Agent 当前不可用");
    }

    private static String traceId() {
        String current = MDC.get("traceId");
        return current == null || current.isBlank() ? UUID.randomUUID().toString() : current;
    }

    private static long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000L;
    }

    private record CancelRequest(
            @com.fasterxml.jackson.annotation.JsonProperty("contract_version") String contractVersion,
            @com.fasterxml.jackson.annotation.JsonProperty("reason_code") String reasonCode) {
    }
}
