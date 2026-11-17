package com.aiep.aihub.web.hr;

import com.aiep.aihub.application.hr.*;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/hr/batch-items")
public class HrRetryController {
  private final HrRetryService service;
  private final HrActorResolver actors;
  private final HrBatchExecutor executor;

  public HrRetryController(
      HrRetryService service, HrActorResolver actors, HrBatchExecutor executor) {
    this.service = service;
    this.actors = actors;
    this.executor = executor;
  }

  @PostMapping("/{id}/retry")
  @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
  public ApiResponse<String> retry(
      @PathVariable String id, @RequestBody HrRetryService.Retry input, HttpServletRequest http) {
    var actor = actors.resolve(http);
    String batch = service.retry(actor, id, input);
    executor.submit(actor, batch);
    return ApiResponse.success(batch);
  }
}
