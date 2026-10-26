package com.aiep.aihub.web.customer;

import com.aiep.aihub.application.customer.CustomerServiceApplicationService;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector;
import com.aiep.aihub.application.customer.CustomerServiceEventProjector.PublicEvent;
import com.aiep.aihub.application.customer.CustomerServiceViews.MessageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.PageView;
import com.aiep.aihub.application.customer.CustomerServiceViews.SubmitView;
import com.aiep.aihub.application.customer.CustomerServiceViews.TimelineView;
import com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.FeedbackPO;
import com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO;
import com.aiep.platformcore.api.ApiResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/customer-service")
public class CustomerServiceController {
    private static final String TENANT = "dev";
    private static final String USER = "1";
    private final CustomerServiceApplicationService service;
    private final CustomerServiceEventProjector projector;

    public CustomerServiceController(CustomerServiceApplicationService service, CustomerServiceEventProjector projector) {
        this.service = service;
        this.projector = projector;
    }

    @PostMapping("/conversations")
    public ApiResponse<ConversationPO> create(@RequestBody CreateConversationRequest request) {
        return ApiResponse.success(service.createConversation(TENANT, USER, request.title()));
    }
    @GetMapping("/conversations")
    public ApiResponse<PageView<ConversationPO>> list(@RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        return ApiResponse.success(service.listConversations(TENANT, USER, keyword, page, pageSize));
    }
    @GetMapping("/conversations/{id}")
    public ApiResponse<ConversationPO> get(@PathVariable String id) { return ApiResponse.success(service.getConversation(TENANT, USER, id)); }
    @PatchMapping("/conversations/{id}")
    public ApiResponse<ConversationPO> update(@PathVariable String id, @RequestBody UpdateConversationRequest request) {
        return ApiResponse.success(service.updateConversation(TENANT, USER, id, request.title(), request.status()));
    }
    @GetMapping("/conversations/{id}/messages")
    public ApiResponse<List<MessageView>> messages(@PathVariable String id,
            @RequestParam(required = false) String beforeMessageId, @RequestParam(defaultValue = "30") int limit) {
        return ApiResponse.success(service.listMessages(TENANT, USER, id, beforeMessageId, limit));
    }
    @PostMapping("/conversations/{id}/messages")
    public ApiResponse<SubmitView> submit(@PathVariable String id, @RequestBody SubmitMessageRequest request) {
        return ApiResponse.success(service.submit(TENANT, USER, id, request.contractVersion(), request.message(), request.clientRequestId()));
    }
    @GetMapping("/runs/{id}")
    public ApiResponse<RunPO> run(@PathVariable String id) { return ApiResponse.success(service.getRun(TENANT, id)); }
    @GetMapping("/runs/{id}/timeline")
    public ApiResponse<TimelineView> timeline(@PathVariable String id) {
        return ApiResponse.success(service.timeline(TENANT, USER, id));
    }
    @GetMapping("/runs/{id}/events")
    public SseEmitter events(@PathVariable String id,
            @RequestHeader(value = "Last-Event-ID", required = false) Long lastEventId,
            @RequestParam(defaultValue = "0") long afterSequence) {
        long after = Math.max(afterSequence, lastEventId == null ? 0 : lastEventId);
        SseEmitter emitter = new SseEmitter(130_000L);
        service.stream(TENANT, id, after).subscribe(event -> {
            PublicEvent projected = projector.project(id, TENANT, event);
            if (projected != null) send(emitter, projected);
        }, emitter::completeWithError, emitter::complete);
        return emitter;
    }
    @PostMapping("/runs/{id}/cancel")
    public ApiResponse<RunPO> cancel(@PathVariable String id) { return ApiResponse.success(service.cancel(TENANT, id)); }
    @PutMapping("/messages/{id}/feedback")
    public ApiResponse<FeedbackPO> feedback(@PathVariable String id, @RequestBody FeedbackRequest request) {
        return ApiResponse.success(service.feedback(TENANT, USER, id, request.rating(), request.reasonCode(), request.comment()));
    }
    @GetMapping("/citations/{id}")
    public ApiResponse<CitationPO> citation(@PathVariable String id) {
        return ApiResponse.success(service.citation(TENANT, id));
    }

    private static void send(SseEmitter emitter, PublicEvent event) {
        try { emitter.send(SseEmitter.event().id(Long.toString(event.sequence())).name(event.eventType()).data(event.payload())); }
        catch (IOException error) { emitter.completeWithError(error); }
    }
    public record CreateConversationRequest(String title) { }
    public record UpdateConversationRequest(String title, String status) { }
    public record SubmitMessageRequest(String contractVersion, String message, String clientRequestId) { }
    public record FeedbackRequest(String rating, String reasonCode, String comment) { }
}
