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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;
import reactor.util.retry.Retry;

@Component
public class HttpAgentClient implements AgentClient {
  @Override public com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt upsertMemoryIndex(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Upsert request) {
    if(request==null||!tenantId.equals(request.scope().tenantId()))throw new AgentTransportException(422,"MEMORY_SCOPE_DENIED","索引范围不匹配");
    var result=memorySemanticPost("upsert",tenantId,request,com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt.class);
    try{result.validate(request);}catch(RuntimeException invalid){throw new AgentTransportException(502,"MEMORY_INDEX_RECEIPT_INVALID","索引回执无效");}return result;
  }
  @Override public com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt deleteMemoryIndex(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Delete request) {
    if(request==null||!tenantId.equals(request.scope().tenantId()))throw new AgentTransportException(422,"MEMORY_SCOPE_DENIED","索引范围不匹配");
    var result=memorySemanticPost("delete",tenantId,request,com.aiep.platformai.api.dto.MemorySemanticTransport.Receipt.class);
    try{result.validate(request);}catch(RuntimeException invalid){throw new AgentTransportException(502,"MEMORY_INDEX_RECEIPT_INVALID","索引回执无效");}return result;
  }
  @Override public com.aiep.platformai.api.dto.MemorySemanticTransport.RecallResult recallMemory(String tenantId,com.aiep.platformai.api.dto.MemorySemanticTransport.Recall request) {
    if(request==null||!tenantId.equals(request.authorization().scope().tenantId()))throw new AgentTransportException(422,"MEMORY_SCOPE_DENIED","召回范围不匹配");
    var result=memorySemanticPost("recall",tenantId,request,com.aiep.platformai.api.dto.MemorySemanticTransport.RecallResult.class);
    try{result.validate(request);}catch(RuntimeException invalid){throw new AgentTransportException(502,"MEMORY_RECALL_RECEIPT_INVALID","召回回执无效");}return result;
  }
  private <T>T memorySemanticPost(String operation,String tenantId,Object body,Class<T> type) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    return requireBody(webClient.post().uri("/internal/v1/memory/index/"+operation).headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
      .contentType(MediaType.APPLICATION_JSON).bodyValue(body).retrieve().onStatus(status->status.isError(),response->downstreamError(response.statusCode().value())).bodyToMono(type));
  }
  private static final Logger log = LoggerFactory.getLogger(HttpAgentClient.class);
  private static final String TENANT_HEADER = "X-Tenant-ID";
  private static final ParameterizedTypeReference<ServerSentEvent<String>> EVENT_TYPE =
      new ParameterizedTypeReference<>() {};

  private final WebClient webClient;
  private final WebClient hrWebClient;
  private final WebClient hrArchiveWebClient;
  private final ObjectMapper objectMapper;
  private final String internalSecret;

  public HttpAgentClient(
      AgentClientProperties properties, WebClient.Builder builder, ObjectMapper objectMapper) {
    HttpClient httpClient =
        HttpClient.create()
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                Math.toIntExact(properties.getConnectTimeout().toMillis()))
            .responseTimeout(properties.getResponseTimeout());
    this.webClient =
        builder
            .baseUrl(properties.getBaseUrl())
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    this.objectMapper = objectMapper;
    this.internalSecret = properties.getInternalSecret();
    HttpClient hrHttpClient =
        HttpClient.create()
            .option(
                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                Math.toIntExact(properties.getConnectTimeout().toMillis()))
            .responseTimeout(java.time.Duration.ofMinutes(10));
    this.hrWebClient =
        builder
            .clone()
            .baseUrl(properties.getBaseUrl())
            .clientConnector(new ReactorClientHttpConnector(hrHttpClient))
            .codecs(codecs -> codecs.defaultCodecs().maxInMemorySize(8 * 1024 * 1024))
            .build();
    ObjectMapper archiveMapper = objectMapper.copy();
    archiveMapper
        .getFactory()
        .setStreamReadConstraints(
            com.fasterxml.jackson.core.StreamReadConstraints.builder()
                .maxStringLength(700 * 1024 * 1024)
                .build());
    this.hrArchiveWebClient =
        builder
            .clone()
            .baseUrl(properties.getBaseUrl())
            .clientConnector(new ReactorClientHttpConnector(hrHttpClient))
            .codecs(
                codecs -> {
                  codecs.defaultCodecs().maxInMemorySize(700 * 1024 * 1024);
                  codecs
                      .defaultCodecs()
                      .jackson2JsonDecoder(
                          new org.springframework.http.codec.json.Jackson2JsonDecoder(
                              archiveMapper));
                })
            .build();
  }

  @Override
  public OperationAgentRunResponse submitOperationMessage(
      String conversationId, OperationAgentMessageRequest request) {
    boolean scoped = request.memoryContext().scope() != null;
    if (scoped && (internalSecret == null || internalSecret.length() < 32 || internalSecret.isBlank()
        || request.tenantId() == null || request.tenantId().isBlank())) {
      throw new AgentTransportException(503, "MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED", "上下文内部调用尚未配置");
    }
    long startedAt = System.nanoTime();
    log.info(
        "event=agent_submit_started conversationId={} requestId={}",
        conversationId,
        request.requestId());
    OperationAgentRunResponse result =
        requireBody(
            webClient
                .post()
                .uri(AgentEndpoints.CONVERSATION_MESSAGES, conversationId)
                .headers(headers -> {
                  if (scoped) headers.setBearerAuth(internalSecret);
                })
                .header(TENANT_HEADER, request.tenantId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .retrieve()
                .onStatus(
                    status -> status.isError(),
                    response -> downstreamError(response.statusCode().value()))
                .bodyToMono(OperationAgentRunResponse.class)
                .retryWhen(Retry.max(1).filter(WebClientRequestException.class::isInstance))
                .onErrorMap(
                    WebClientRequestException.class,
                    error ->
                        new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用")));
    log.info(
        "event=agent_submit_succeeded conversationId={} agentRunId={} status={} elapsedMs={}",
        conversationId,
        result.runId(),
        result.status(),
        elapsedMillis(startedAt));
    return result;
  }

  @Override
  public com.aiep.platformai.api.dto.MemoryContextWait queryMemoryWait(String tenantId,String executionId) {
    return queryMemoryWait(tenantId,executionId,null);
  }
  @Override
  public com.aiep.platformai.api.dto.MemoryContextWait queryMemoryWait(String tenantId,String executionId,String eventRef) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    return requireBody(webClient.get().uri(uri->{
      var route=uri.path("/internal/v1/memory/executions/{execution}/wait");
      if(eventRef!=null)route.queryParam("wait_event_id",eventRef);
      return route.build(executionId);
    })
      .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
      .retrieve().onStatus(status->status.isError(),response->downstreamError(response.statusCode().value()))
      .bodyToMono(com.aiep.platformai.api.dto.MemoryContextWait.class));
  }

  @Override
  public com.aiep.platformai.api.dto.MemoryRuntimeManifest queryMemoryManifest(String tenantId,String executionId) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    return requireBody(webClient.get().uri("/internal/v1/memory/executions/{execution}/manifest",executionId)
      .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
      .retrieve().onStatus(status->status.isError(),response->downstreamError(response.statusCode().value()))
      .bodyToMono(com.aiep.platformai.api.dto.MemoryRuntimeManifest.class));
  }

  @Override
  public com.aiep.platformai.api.dto.MemoryResumeReceipt resumeMemoryExecution(String tenantId,String executionId,com.aiep.platformai.api.dto.MemoryResumeRequest request) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    return requireBody(webClient.post().uri("/internal/v1/memory/executions/{execution}/resume",executionId)
      .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId).bodyValue(request)
      .exchangeToMono(response->{
        int status=response.statusCode().value();
        if(status!=200&&status!=202&&status!=409&&status!=503)return response.releaseBody().then(Mono.error(new AgentTransportException(status,"AGENT_REQUEST_FAILED","Agent 请求失败")));
        return response.bodyToMono(com.aiep.platformai.api.dto.MemoryResumeReceipt.class).flatMap(receipt->{
          if(receipt.state()!=null&&receipt.resultCode().httpStatus()!=status)
            return Mono.error(new AgentTransportException(502,"MEMORY_RECEIPT_INVALID","上下文回执无效"));
          return Mono.just(receipt);
        });
      }));
  }

  @Override
  public com.aiep.platformai.api.dto.MemoryCleanupReceipt cleanupMemoryExecution(String tenantId,String executionId,com.aiep.platformai.api.dto.MemoryCleanupRequest request) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    return requireBody(webClient.post().uri("/internal/v1/memory/executions/{execution}/cleanup",executionId)
      .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId).bodyValue(request)
      .retrieve().onStatus(status->status.isError(),response->downstreamError(response.statusCode().value()))
      .bodyToMono(com.aiep.platformai.api.dto.MemoryCleanupReceipt.class));
  }

  @Override
  public Flux<OperationAgentRunEvent> streamOperationRunEvents(
      String runId, String tenantId, long afterSequence) {
    WebClient.RequestHeadersSpec<?> request =
        webClient
            .get()
            .uri(AgentEndpoints.RUN_EVENTS, runId)
            .header(TENANT_HEADER, tenantId)
            .accept(MediaType.TEXT_EVENT_STREAM);
    if (afterSequence > 0) {
      request = request.header("Last-Event-ID", Long.toString(afterSequence));
    }
    log.info("event=agent_sse_connecting agentRunId={} afterSequence={}", runId, afterSequence);
    return request
        .retrieve()
        .onStatus(
            status -> status.isError(), response -> downstreamError(response.statusCode().value()))
        .bodyToFlux(EVENT_TYPE)
        .filter(event -> event.data() != null)
        .map(event -> Objects.requireNonNull(event.data()))
        .map(this::decodeEvent)
        .doOnNext(
            event ->
                log.info(
                    "event=agent_sse_event agentRunId={} sequence={} type={}",
                    runId,
                    event.sequence(),
                    event.event()))
        .doOnComplete(() -> log.info("event=agent_sse_completed agentRunId={}", runId))
        .doOnError(
            error ->
                log.error(
                    "event=agent_sse_failed agentRunId={} errorType={}",
                    runId,
                    error.getClass().getSimpleName()))
        .onErrorMap(
            WebClientRequestException.class,
            error -> new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用"));
  }

  @Override
  public OperationAgentCancelResponse cancelOperationRun(String runId, String tenantId) {
    long startedAt = System.nanoTime();
    OperationAgentCancelResponse result =
        requireBody(
            webClient
                .post()
                .uri(AgentEndpoints.RUN_CANCEL, runId)
                .header(TENANT_HEADER, tenantId)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CancelRequest("run.cancel/1", tenantId, "user_requested"))
                .retrieve()
                .onStatus(
                    status -> status.isError(),
                    response -> downstreamError(response.statusCode().value()))
                .bodyToMono(OperationAgentCancelResponse.class)
                .onErrorMap(
                    WebClientRequestException.class,
                    error ->
                        new AgentTransportException(503, "AGENT_UNAVAILABLE", "Agent 服务当前不可用")));
    log.info(
        "event=agent_cancel_succeeded agentRunId={} status={} elapsedMs={}",
        runId,
        result.status(),
        elapsedMillis(startedAt));
    return result;
  }

  @Override
  public AiTextResponse generateText(AiTextRequest request) {
    return post(AgentEndpoints.TEXT_GENERATE, request, AiTextResponse.class);
  }

  @Override
  public AiTextResponse executeSkill(AiSkillExecuteRequest request) {
    if (request.skillId() != null && request.skillId() >= 6101 && request.skillId() <= 6110) {
      if (internalSecret == null
          || internalSecret.length() < 32
          || request.tenantId() == null
          || request.tenantId().isBlank())
        throw new AgentTransportException(503, "HR_INTERNAL_AUTH_CONFIG_REQUIRED", "人事内部调用尚未配置");
      return requireBody(
          (rawArchive(request) ? hrArchiveWebClient : hrWebClient)
              .post()
              .uri(AgentEndpoints.SKILL_EXECUTE)
              .header("Authorization", "Bearer " + internalSecret)
              .header(TENANT_HEADER, request.tenantId())
              .contentType(MediaType.APPLICATION_JSON)
              .bodyValue(request)
              .retrieve()
              .onStatus(
                  status -> status.isError(),
                  response ->
                      response
                          .bodyToMono(String.class)
                          .defaultIfEmpty("")
                          .map(body -> skillError(response.statusCode().value(), body)))
              .bodyToMono(AiTextResponse.class)
              .timeout(java.time.Duration.ofMinutes(10)));
    }
    return post(AgentEndpoints.SKILL_EXECUTE, request, AiTextResponse.class);
  }

  @Override
  public com.aiep.platformai.api.dto.MemoryDeriveRequest queryMemoryDerivePlan(String tenantId,String executionId) {
    requireMemoryDeriveIdentity(tenantId,executionId);
    String raw=requireBody(webClient.get().uri("/internal/v1/memory/executions/{execution}/derive-plan",executionId)
        .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
        .retrieve().onStatus(status->status.isError(),response->response.bodyToMono(String.class)
            .defaultIfEmpty("").map(value->memoryDeriveError(response.statusCode().value(),value)))
        .bodyToMono(String.class)
        .onErrorMap(error->!(error instanceof AgentTransportException),error->new AgentTransportException(503,"AGENT_UNAVAILABLE","摘要计划读取未完成")));
    try {
      var strict=objectMapper.copy().enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY)
          .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
      var request=strict.readValue(raw,com.aiep.platformai.api.dto.MemoryDeriveRequest.class);
      if(request==null||!executionId.equals(request.executionScope().executionId()))
        throw new IllegalArgumentException("DERIVE_BINDING_CONFLICT");
      request.validateBinding(tenantId);
      return request;
    } catch(java.io.IOException|IllegalArgumentException error) {
      throw new AgentTransportException(502,"MEMORY_DERIVE_PLAN_INVALID","摘要计划绑定无效");
    }
  }

  @Override
  public void finishMemoryDerive(String tenantId,String executionId,String planId,String planFingerprint,String status) {
    requireMemoryDeriveIdentity(tenantId,executionId);
    if(planId==null||planId.isBlank()||planId.codePointCount(0,planId.length())>128
        ||planFingerprint==null||!planFingerprint.matches("[0-9a-f]{64}")
        ||!("COMMITTED".equals(status)||"REJECTED".equals(status)))
      throw new AgentTransportException(422,"MEMORY_DERIVE_CONTRACT_INVALID","摘要完成通知无效");
    String raw=requireBody(webClient.post().uri("/internal/v1/memory/executions/{execution}/derive-finish",executionId)
        .headers(headers->headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
        .contentType(MediaType.APPLICATION_JSON).bodyValue(new MemoryDeriveFinish(planId,planFingerprint,status))
        .retrieve().onStatus(value->value.isError(),response->response.bodyToMono(String.class)
            .defaultIfEmpty("").map(value->memoryDeriveError(response.statusCode().value(),value)))
        .bodyToMono(String.class)
        .onErrorMap(error->!(error instanceof AgentTransportException),error->new AgentTransportException(503,"DERIVE_TRANSPORT_UNKNOWN","摘要完成通知结果尚未确定")));
    try {
      var strict=objectMapper.copy().enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY)
          .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
      var receipt=strict.readTree(raw);
      if(receipt==null||!receipt.isObject()||receipt.size()!=1||!receipt.path("code").isTextual()
          ||!"MEMORY_DERIVE_FINISHED".equals(receipt.path("code").textValue()))
        throw new IllegalArgumentException("MEMORY_DERIVE_FINISH_INVALID");
    } catch(java.io.IOException|IllegalArgumentException error) {
      throw new AgentTransportException(502,"MEMORY_DERIVE_FINISH_INVALID","摘要完成通知回执无效");
    }
  }

  private void requireMemoryDeriveIdentity(String tenantId,String executionId) {
    if(internalSecret==null||internalSecret.isBlank()||internalSecret.length()<32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    if(tenantId==null||tenantId.isBlank()||executionId==null||executionId.isBlank()
        ||tenantId.codePointCount(0,tenantId.length())>128||executionId.codePointCount(0,executionId.length())>128)
      throw new AgentTransportException(422,"MEMORY_DERIVE_CONTRACT_INVALID","摘要执行身份无效");
  }

  private record MemoryDeriveFinish(
      @com.fasterxml.jackson.annotation.JsonProperty("plan_id") String planId,
      @com.fasterxml.jackson.annotation.JsonProperty("plan_fingerprint") String planFingerprint,String status) { }

  @Override
  public com.aiep.platformai.api.dto.MemoryDeriveResponse deriveMemory(
      String tenantId, com.aiep.platformai.api.dto.MemoryDeriveRequest request) {
    if (internalSecret == null || internalSecret.isBlank() || internalSecret.length() < 32)
      throw new AgentTransportException(503,"MEMORY_INTERNAL_AUTH_CONFIG_REQUIRED","上下文内部调用尚未配置");
    if (request == null) throw new AgentTransportException(422,"MEMORY_DERIVE_CONTRACT_INVALID","摘要计划无效");
    try { request.validateBinding(tenantId); }
    catch (IllegalArgumentException error) { throw new AgentTransportException(409,"DERIVE_BINDING_CONFLICT","摘要计划绑定无效"); }
    if (request.deadlineEpochSeconds() <= java.time.Instant.now().getEpochSecond())
      throw new AgentTransportException(409,"DERIVE_DEADLINE_EXCEEDED","摘要执行已截止");
    String input;
    try { input = objectMapper.writeValueAsString(request); }
    catch (JsonProcessingException error) { throw new AgentTransportException(422,"MEMORY_DERIVE_CONTRACT_INVALID","摘要计划无效"); }
    var body = new MemorySkillBody(new MemorySkillContext(request.operationId(),
        request.executionScope().conversation().userId(),request.executionScope().conversation().domain(),"memory.derive"),6201,input);
    try {
      if (objectMapper.writeValueAsBytes(body).length > 1048576)
        throw new AgentTransportException(413,"MEMORY_DERIVE_HTTP_SIZE_LIMIT","摘要计划超过传输上限");
    } catch (JsonProcessingException error) {
      throw new AgentTransportException(422,"MEMORY_DERIVE_CONTRACT_INVALID","摘要计划无效");
    }
    // 网络未知不能换task重试；原op的持久重放由执行端处理。
    String raw = requireBody(webClient.post().uri(AgentEndpoints.SKILL_EXECUTE)
        .headers(headers -> headers.setBearerAuth(internalSecret)).header(TENANT_HEADER,tenantId)
        .contentType(MediaType.APPLICATION_JSON).bodyValue(body).retrieve()
        .onStatus(status -> status.isError(), response -> response.bodyToMono(String.class)
            .defaultIfEmpty("").map(value -> memoryDeriveError(response.statusCode().value(),value)))
        .bodyToMono(String.class)
        .timeout(java.time.Duration.ofSeconds(Math.max(1,request.deadlineEpochSeconds()-java.time.Instant.now().getEpochSecond())))
        .onErrorMap(WebClientRequestException.class,error -> new AgentTransportException(503,"AGENT_UNAVAILABLE","Agent 服务当前不可用"))
        .onErrorMap(java.util.concurrent.TimeoutException.class,error -> new AgentTransportException(504,"DERIVE_TRANSPORT_UNKNOWN","摘要结果尚未确定"))
        .onErrorMap(error -> !(error instanceof AgentTransportException),error -> new AgentTransportException(502,"DERIVE_TRANSPORT_UNKNOWN","摘要结果尚未确定")));
    try {
      ObjectMapper strict = objectMapper.copy().enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_READING_DUP_TREE_KEY);
      var outer = strict.readTree(raw);
      if (!outer.isObject() || outer.size()!=1 || !outer.path("content").isTextual())
        throw new IllegalArgumentException("MEMORY_DERIVE_RESPONSE_INVALID");
      var result = strict.readValue(outer.path("content").textValue(),com.aiep.platformai.api.dto.MemoryDeriveResponse.class);
      result.validateBinding(request);
      return result;
    } catch (java.io.IOException | IllegalArgumentException error) {
      throw new AgentTransportException(502,"MEMORY_DERIVE_RESPONSE_INVALID","摘要返回绑定无效");
    }
  }

  private AgentTransportException memoryDeriveError(int status,String body) {
    String code="AGENT_REQUEST_FAILED";
    try {
      String supplied=objectMapper.readTree(body).path("code").asText();
      if(supplied.matches("(?:MEMORY_|DERIVE_|SUMMARY_|CONTEXT_|PAID_|PROVIDER_|AGENT_|BUDGET_|RUN_|WORKLOAD_|LEDGER_|NO_BUDGET|UNKNOWN_PRICE|INVALID_PLAN|INVALID_PRICE|PAYLOAD_LIMIT)[A-Z0-9_]*")) code=supplied;
    } catch(java.io.IOException | RuntimeException ignored) { }
    return new AgentTransportException(status,code,"摘要处理未完成");
  }

  private record MemorySkillContext(String traceId,String userId,String sourceModule,String actionType) { }
  private record MemorySkillBody(MemorySkillContext context,int skillId,String input) {
    @Override public String toString() { return "MemorySkillBody[redacted]"; }
  }

  private boolean rawArchive(AiSkillExecuteRequest request) {
    if (!Long.valueOf(6101).equals(request.skillId())) return false;
    try {
      ObjectMapper requestMapper = objectMapper.copy();
      requestMapper
          .getFactory()
          .setStreamReadConstraints(
              com.fasterxml.jackson.core.StreamReadConstraints.builder()
                  .maxStringLength(140 * 1024 * 1024)
                  .build());
      return requestMapper
          .readTree(request.input())
          .path("extraction")
          .path("archive_raw")
          .asBoolean(false);
    } catch (JsonProcessingException error) {
      return false;
    }
  }

  @Override
  public AiTaskStatusResponse submitIngest(AiIngestRequest request) {
    return post(AgentEndpoints.KB_INGEST, request, AiTaskStatusResponse.class);
  }

  @Override
  public AiTaskStatusResponse queryTask(String taskId) {
    return requireBody(
        webClient
            .get()
            .uri(AgentEndpoints.TASK_QUERY, taskId)
            .retrieve()
            .onStatus(
                status -> status.isError(),
                response -> downstreamError(response.statusCode().value()))
            .bodyToMono(AiTaskStatusResponse.class));
  }

  @Override
  public void deleteVectors(AiVectorDeleteRequest request) {
    requireBody(
        webClient
            .method(org.springframework.http.HttpMethod.DELETE)
            .uri(AgentEndpoints.KB_VECTORS)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .onStatus(
                status -> status.isError(),
                response -> downstreamError(response.statusCode().value()))
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
    return requireBody(
        webClient
            .post()
            .uri(path)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .onStatus(
                status -> status.isError(),
                response -> downstreamError(response.statusCode().value()))
            .bodyToMono(responseType));
  }

  private static Mono<? extends Throwable> downstreamError(int statusCode) {
    return Mono.just(new AgentTransportException(statusCode, "AGENT_REQUEST_FAILED", "Agent 请求失败"));
  }

  private AgentTransportException skillError(int status, String body) {
    String code = "AGENT_REQUEST_FAILED";
    try {
      String supplied = objectMapper.readTree(body).path("code").asText();
      if (supplied.matches(
          "(?:HR_|PAID_|AGENT_|PROVIDER_|PROMPT_|BUDGET_|RUN_|WORKLOAD_|LEDGER_|NO_BUDGET|UNKNOWN_PRICE|INVALID_PLAN|INVALID_PRICE|PAYLOAD_LIMIT)[A-Z0-9_]*"))
        code = supplied;
    } catch (java.io.IOException ignored) {
    }
    return new AgentTransportException(status, code, "人事智能处理未完成");
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

  private static long elapsedMillis(long startedAtNanos) {
    return (System.nanoTime() - startedAtNanos) / 1_000_000L;
  }

  private record CancelRequest(
      @com.fasterxml.jackson.annotation.JsonProperty("contract_version") String contractVersion,
      @com.fasterxml.jackson.annotation.JsonProperty("tenant_id") String tenantId,
      @com.fasterxml.jackson.annotation.JsonProperty("reason_code") String reasonCode) {}
}

