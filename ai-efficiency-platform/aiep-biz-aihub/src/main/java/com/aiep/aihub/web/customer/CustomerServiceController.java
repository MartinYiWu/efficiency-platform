package com.aiep.aihub.web.customer;

import com.aiep.aihub.web.memory.MemoryActorResolver;
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
import org.springframework.web.bind.annotation.DeleteMapping;
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
    private final MemoryActorResolver actors;
    private final CustomerServiceApplicationService service;
    private final CustomerServiceEventProjector projector;

    public CustomerServiceController(CustomerServiceApplicationService service, CustomerServiceEventProjector projector, MemoryActorResolver actors) {
        this.actors = actors;
        this.service = service;
        this.projector = projector;
    }

    @PostMapping("/conversations")
    public ApiResponse<ConversationPO> create(@RequestBody CreateConversationRequest request) {
        var actor = actors.current();
        return ApiResponse.success(service.createConversation(actor.tenantId(), actor.userId(), request.title()));
    }
    @GetMapping("/conversations")
    public ApiResponse<PageView<ConversationPO>> list(@RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int page, @RequestParam(defaultValue = "20") int pageSize) {
        var actor = actors.current();
        return ApiResponse.success(service.listConversations(actor.tenantId(), actor.userId(), keyword, page, pageSize));
    }
    @GetMapping("/conversations/{id}")
    public ApiResponse<ConversationPO> get(@PathVariable String id) {
        var actor = actors.current(); return ApiResponse.success(service.getConversation(actor.tenantId(), actor.userId(), id)); }
    @PatchMapping("/conversations/{id}")
    public ApiResponse<ConversationPO> update(@PathVariable String id, @RequestBody UpdateConversationRequest request) {
        var actor = actors.current();
        return ApiResponse.success(service.updateConversation(actor.tenantId(), actor.userId(), id, request.title(), request.status()));
    }
    @DeleteMapping("/conversations/{id}")
    public ApiResponse<Boolean> delete(@PathVariable String id) {
        var actor = actors.current();
        service.deleteConversation(actor.tenantId(), actor.userId(), id);
        return ApiResponse.success(true);
    }
    @GetMapping("/conversations/{id}/messages")
    public ApiResponse<List<MessageView>> messages(@PathVariable String id,
            @RequestParam(required = false) String beforeMessageId, @RequestParam(defaultValue = "30") int limit) {
        var actor = actors.current();
        return ApiResponse.success(service.listMessages(actor.tenantId(), actor.userId(), id, beforeMessageId, limit));
    }
    @PostMapping("/conversations/{id}/messages")
    public ApiResponse<SubmitView> submit(@PathVariable String id, @RequestBody SubmitMessageRequest request) {
        var actor = actors.current();
        return ApiResponse.success(service.submit(actor.tenantId(), actor.userId(), id, request.contractVersion(), request.message(), request.clientRequestId()));
    }
    @GetMapping("/runs/{id}")
    public ApiResponse<RunPO> run(@PathVariable String id) {
        var actor = actors.current(); return ApiResponse.success(service.getRun(actor.tenantId(), actor.userId(), id)); }
    @GetMapping("/runs/{id}/timeline")
    public ApiResponse<TimelineView> timeline(@PathVariable String id) {
        var actor = actors.current();
        return ApiResponse.success(service.timeline(actor.tenantId(), actor.userId(), id));
    }
    @GetMapping("/runs/{id}/events")
    public SseEmitter events(@PathVariable String id,
            @RequestHeader(value = "Last-Event-ID", required = false) Long lastEventId,
            @RequestParam(defaultValue = "0") long afterSequence) {
        var actor = actors.current();
        long after = Math.max(afterSequence, lastEventId == null ? 0 : lastEventId);
        SseEmitter emitter = new SseEmitter(130_000L);
        if (com.aiep.aihub.domain.customer.CustomerServiceModels.TERMINAL_STATUSES.contains(service.getRun(actor.tenantId(), actor.userId(), id).status())) {
            projector.replay(id, actor.tenantId(), after).forEach(event -> send(emitter, event));
            emitter.complete();
            return emitter;
        }
        service.stream(actor.tenantId(), actor.userId(), id, after)
            .publishOn(reactor.core.scheduler.Schedulers.boundedElastic()).subscribe(event -> {
            actors.revalidate(actor);
            service.getRun(actor.tenantId(), actor.userId(), id);
            PublicEvent projected = projector.project(id, actor.tenantId(), event);
            if("context_refresh_required".equals(event.eventType())) {
                projector.onMemoryWait(id,event,actor);return;
            }
            if("memory_derive_required".equals(event.eventType())) {projector.onMemoryDerive(id,event,actor);return;}
            if (projected != null) send(emitter, projected);
        }, emitter::completeWithError, emitter::complete);
        return emitter;
    }
    @PostMapping("/runs/{id}/cancel")
    public ApiResponse<RunPO> cancel(@PathVariable String id) {
        var actor = actors.current(); return ApiResponse.success(service.cancel(actor.tenantId(), actor.userId(), id)); }
    @PutMapping("/messages/{id}/feedback")
    public ApiResponse<FeedbackPO> feedback(@PathVariable String id, @RequestBody FeedbackRequest request) {
        var actor = actors.current();
        return ApiResponse.success(service.feedback(actor.tenantId(), actor.userId(), id, request.rating(), request.reasonCode(), request.comment()));
    }
    @GetMapping("/citations/{id}")
    public ApiResponse<CitationPO> citation(@PathVariable String id) {
        var actor = actors.current();
        return ApiResponse.success(service.citation(actor.tenantId(), actor.userId(), id));
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
