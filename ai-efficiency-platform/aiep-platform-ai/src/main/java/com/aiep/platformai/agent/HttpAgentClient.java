package com.aiep.platformai.agent;

import com.aiep.platformai.api.dto.AiIngestRequest;
import com.aiep.platformai.api.dto.AiKbQaRequest;
import com.aiep.platformai.api.dto.AiSkillExecuteRequest;
import com.aiep.platformai.api.dto.AiStreamObserver;
import com.aiep.platformai.api.dto.AiStreamRequest;
import com.aiep.platformai.api.dto.AiTaskStatusResponse;
import com.aiep.platformai.api.dto.AiTextRequest;
import com.aiep.platformai.api.dto.AiTextResponse;
import com.aiep.platformai.api.dto.AiVectorDeleteRequest;
import com.aiep.platformai.api.dto.OperationAgentCancelResponse;
import com.aiep.platformai.api.dto.OperationAgentMessageRequest;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformai.api.dto.OperationAgentRunResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.netty.channel.ChannelOption;
import java.util.Objects;
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

@Component
public class HttpAgentClient implements AgentClient {
    private static final String TENANT_HEADER = "X-Tenant-ID";
    private static final ParameterizedTypeReference<ServerSentEvent<String>> EVENT_TYPE =
            new ParameterizedTypeReference<>() { };

    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    public HttpAgentClient(
            AgentClientProperties properties, WebClient.Builder builder, ObjectMapper objectMapper) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, Math.toIntExact(properties.getConnectTimeout().toMillis()))
                .responseTimeout(properties.getResponseTimeout());
        this.webClient = builder
                .baseUrl(properties.getBaseUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
        this.objectMapper = objectMapper;
    }

    @Override
    public OperationAgentRunResponse submitOperationMessage(
            String conversationId, OperationAgentMessageRequest request) {
        return requireBody(webClient.post()
                .uri(AgentEndpoints.CONVERSATION_MESSAGES, conversationId)
                .header(TENANT_HEADER, request.tenantId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToMono(OperationAgentRunResponse.class)
                .retryWhen(Retry.max(1).filter(WebClientRequestException.class::isInstance))
                .onErrorMap(WebClientRequestException.class,
                        error -> new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用")));
    }

    @Override
    public Flux<OperationAgentRunEvent> streamOperationRunEvents(
            String runId, String tenantId, long afterSequence) {
        WebClient.RequestHeadersSpec<?> request = webClient.get()
                .uri(AgentEndpoints.RUN_EVENTS, runId)
                .header(TENANT_HEADER, tenantId)
                .accept(MediaType.TEXT_EVENT_STREAM);
        if (afterSequence > 0) {
            request = request.header("Last-Event-ID", Long.toString(afterSequence));
        }
        return request.retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToFlux(EVENT_TYPE)
                .filter(event -> event.data() != null)
                .map(event -> Objects.requireNonNull(event.data()))
                .map(this::decodeEvent)
                .onErrorMap(WebClientRequestException.class,
                        error -> new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用"));
    }

    @Override
    public OperationAgentCancelResponse cancelOperationRun(String runId, String tenantId) {
        return requireBody(webClient.post()
                .uri(AgentEndpoints.RUN_CANCEL, runId)
                .header(TENANT_HEADER, tenantId)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CancelRequest("run.cancel/1", tenantId, "user_requested"))
                .retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToMono(OperationAgentCancelResponse.class)
                .onErrorMap(WebClientRequestException.class,
                        error -> new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用")));
    }

    @Override
    public AiTextResponse generateText(AiTextRequest request) {
        return post(AgentEndpoints.TEXT_GENERATE, request, AiTextResponse.class);
    }

    @Override
    public AiTextResponse executeSkill(AiSkillExecuteRequest request) {
        return post(AgentEndpoints.SKILL_EXECUTE, request, AiTextResponse.class);
    }

    @Override
    public AiTaskStatusResponse submitIngest(AiIngestRequest request) {
        return post(AgentEndpoints.KB_INGEST, request, AiTaskStatusResponse.class);
    }

    @Override
    public AiTaskStatusResponse queryTask(String taskId) {
        return requireBody(webClient.get().uri(AgentEndpoints.TASK_QUERY, taskId)
                .retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToMono(AiTaskStatusResponse.class));
    }

    @Override
    public void deleteVectors(AiVectorDeleteRequest request) {
        requireBody(webClient.method(org.springframework.http.HttpMethod.DELETE)
                .uri(AgentEndpoints.KB_VECTORS)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .toBodilessEntity());
    }

    @Override
    public void streamChat(AiStreamRequest request, AiStreamObserver observer) {
        throw new UnsupportedOperationException("旧版流式聊天协议尚未启用");
    }

    @Override
    public void streamKbQa(AiKbQaRequest request, AiStreamObserver observer) {
        throw new UnsupportedOperationException("旧版知识库流式协议尚未启用");
    }

    private <T> T post(String path, Object request, Class<T> responseType) {
        return requireBody(webClient.post().uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .onStatus(status -> status.isError(), response -> downstreamError(response.statusCode().value()))
                .bodyToMono(responseType));
    }

    private static Mono<? extends Throwable> downstreamError(int statusCode) {
        return Mono.just(new AgentTransportException(statusCode, "AGENT_REQUEST_FAILED", "Agent 请求失败"));
    }

    private OperationAgentRunEvent decodeEvent(String value) {
        try {
            return objectMapper.readValue(value, OperationAgentRunEvent.class);
        } catch (JsonProcessingException exception) {
            throw new AgentTransportException(502, "AGENT_EVENT_INVALID", "Agent 事件格式无效");
        }
    }

    private static <T> T requireBody(Mono<T> publisher) {
        T value = publisher.block();
        if (value == null) {
            throw new AgentTransportException(502, "AGENT_EMPTY_RESPONSE", "Agent 返回空响应");
        }
        return value;
    }

    private record CancelRequest(
            @com.fasterxml.jackson.annotation.JsonProperty("contract_version") String contractVersion,
            @com.fasterxml.jackson.annotation.JsonProperty("tenant_id") String tenantId,
            @com.fasterxml.jackson.annotation.JsonProperty("reason_code") String reasonCode) {
    }
}
