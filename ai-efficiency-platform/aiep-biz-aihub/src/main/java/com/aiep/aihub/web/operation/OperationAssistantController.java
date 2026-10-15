package com.aiep.aihub.web.operation;

import com.aiep.aihub.application.operation.OperationAssistantService;
import com.aiep.aihub.application.operation.OperationViews;
import com.aiep.platformai.api.dto.OperationAgentRunEvent;
import com.aiep.platformcore.api.ApiResponse;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.Disposable;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/operations")
public class OperationAssistantController {
    private static final long SSE_TIMEOUT_MILLIS = 10 * 60 * 1000L;

    private final OperationAssistantService service;

    public OperationAssistantController(OperationAssistantService service) {
        this.service = service;
    }

    @PostMapping("/conversations")
    public ApiResponse<OperationViews.ConversationView> createConversation(
            @RequestBody(required = false) CreateConversationRequest request) {
        return ApiResponse.success(service.createConversation(request == null ? null : request.title()));
    }

    @PostMapping("/conversations/{conversationId}/messages")
    public ResponseEntity<ApiResponse<OperationViews.RunView>> submitMessage(
            @PathVariable String conversationId,
            @RequestBody SubmitMessageRequest request) {
        String clientRequestId = request.clientRequestId() == null || request.clientRequestId().isBlank()
                ? UUID.randomUUID().toString()
                : request.clientRequestId();
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(ApiResponse.success(service.submitMessage(conversationId, request.message(), clientRequestId)));
    }

    @GetMapping("/conversations/{conversationId}")
    public ApiResponse<OperationViews.ConversationView> getConversation(@PathVariable String conversationId) {
        return ApiResponse.success(service.getConversation(conversationId));
    }

    @GetMapping("/conversations/{conversationId}/messages")
    public ApiResponse<OperationViews.MessageListView> listMessages(@PathVariable String conversationId) {
        return ApiResponse.success(service.listMessages(conversationId));
    }

    @GetMapping("/runs/{runId}")
    public ApiResponse<OperationViews.RunView> getRun(@PathVariable String runId) {
        return ApiResponse.success(service.getRun(runId));
    }

    @GetMapping(path = "/runs/{runId}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamEvents(
            @PathVariable String runId,
            @RequestParam(defaultValue = "0") long afterSequence) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT_MILLIS);
        Disposable subscription = service.streamRunEvents(runId, afterSequence)
                .publishOn(Schedulers.boundedElastic())
                .subscribe(
                        event -> sendEvent(emitter, runId, event),
                        emitter::completeWithError,
                        emitter::complete);
        emitter.onCompletion(subscription::dispose);
        emitter.onTimeout(subscription::dispose);
        emitter.onError(error -> subscription.dispose());
        return emitter;
    }

    @PostMapping("/runs/{runId}/cancel")
    public ApiResponse<OperationViews.RunView> cancelRun(@PathVariable String runId) {
        return ApiResponse.success(service.cancelRun(runId));
    }

    @GetMapping("/conversations/{conversationId}/artifacts")
    public ApiResponse<OperationViews.ArtifactListView> listArtifacts(@PathVariable String conversationId) {
        return ApiResponse.success(service.listArtifacts(conversationId));
    }

    @GetMapping("/artifacts/{artifactId}")
    public ApiResponse<OperationViews.ArtifactView> getArtifact(@PathVariable String artifactId) {
        return ApiResponse.success(service.getArtifact(artifactId));
    }

    @GetMapping(path = "/artifacts/{artifactId}/copy", produces = MediaType.TEXT_PLAIN_VALUE)
    public String copyArtifact(@PathVariable String artifactId) {
        return service.getArtifact(artifactId).bodyMarkdown();
    }

    @GetMapping(path = {"/artifacts/{artifactId}/wechat-html", "/artifacts/{artifactId}/html"},
            produces = MediaType.TEXT_HTML_VALUE)
    public String previewArtifact(@PathVariable String artifactId) {
        return service.getArtifact(artifactId).bodyHtml();
    }

    @GetMapping(path = "/artifacts/{artifactId}/download", produces = "text/markdown;charset=UTF-8")
    public ResponseEntity<byte[]> downloadArtifact(@PathVariable String artifactId) {
        OperationViews.ArtifactView artifact = service.getArtifact(artifactId);
        String filename = "operation-article-" + artifact.artifactId() + ".md";
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment().filename(filename, StandardCharsets.UTF_8).build().toString())
                .body(artifact.bodyMarkdown().getBytes(StandardCharsets.UTF_8));
    }

    private void sendEvent(SseEmitter emitter, String runId, OperationAgentRunEvent event) {
        try {
            service.projectEvent(runId, event);
            OperationAgentRunEvent publicEvent = new OperationAgentRunEvent(
                    event.contractVersion(), event.event(), runId, event.sequence(), event.payload());
            emitter.send(SseEmitter.event()
                    .id(Long.toString(event.sequence()))
                    .name(event.event())
                    .data(publicEvent, MediaType.APPLICATION_JSON));
        } catch (Exception exception) {
            emitter.completeWithError(exception);
        }
    }

    public record CreateConversationRequest(String title) { }
    public record SubmitMessageRequest(String message, String clientRequestId) { }
}
