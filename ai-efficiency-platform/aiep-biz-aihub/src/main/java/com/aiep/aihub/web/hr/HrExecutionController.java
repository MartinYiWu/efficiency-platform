package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrExecutionContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/hr")
public class HrExecutionController {
  private final HrExecutionService service;
  private final HrActorResolver actors;

  public HrExecutionController(HrExecutionService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/matching-results/{id}/feedback")
  public ApiResponse<Feedback> feedback(
      @PathVariable String id, @RequestBody FeedbackRequest input, HttpServletRequest http) {
    return ApiResponse.success(service.feedback(actors.resolve(http), id, input));
  }

  @GetMapping("/matching-results/{id}/feedback")
  public ApiResponse<List<Feedback>> feedbacks(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.feedbacks(actors.resolve(http), id));
  }

  @GetMapping(value = "/matching-runs/{id}/events", produces = "text/event-stream")
  public SseEmitter events(
      @PathVariable String id,
      @RequestHeader(value = "Last-Event-ID", required = false) String last,
      @RequestParam(defaultValue = "0") long afterSequence,
      HttpServletRequest http) {
    var actor = actors.resolve(http);
    long after = last == null ? afterSequence : Long.parseLong(last);
    var initial = service.events(actor, id, after);
    SseEmitter emitter = new SseEmitter(600000L);
    var cancelled = new java.util.concurrent.atomic.AtomicBoolean();
    emitter.onCompletion(() -> cancelled.set(true));
    emitter.onTimeout(() -> cancelled.set(true));
    Thread.startVirtualThread(
        () -> {
          long cursor = after;
          long until = System.nanoTime() + java.time.Duration.ofMinutes(10).toNanos();
          try {
            var rows = initial;
            while (!cancelled.get() && System.nanoTime() < until) {
              for (var r : rows) {
                emitter.send(
                    SseEmitter.event()
                        .id(Long.toString(r.sequence()))
                        .name("status")
                        .data(
                            new com.aiep.aihub.api.hr.HrCandidateContracts.RunView(
                                r.runId(), r.status(), r.resultId(), r.failureCode())));
                cursor = r.sequence();
                if (cursor == 4) {
                  emitter.complete();
                  return;
                }
              }
              Thread.sleep(1000);
              rows = service.events(actor, id, cursor);
            }
            emitter.complete();
          } catch (Exception e) {
            emitter.completeWithError(e);
          }
        });
    return emitter;
  }
}
