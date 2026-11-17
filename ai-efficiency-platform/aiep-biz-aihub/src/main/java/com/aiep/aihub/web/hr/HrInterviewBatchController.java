package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrInterviewBatchContracts.*;
import com.aiep.aihub.application.hr.HrInterviewBatchService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/hr")
public class HrInterviewBatchController {
  private final HrInterviewBatchService service;
  private final HrActorResolver actors;

  public HrInterviewBatchController(HrInterviewBatchService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/interview-batches")
  @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
  public ApiResponse<Batch> generate(
      @RequestBody GenerationBatch input,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    return ApiResponse.success(service.generate(actors.resolve(http), input, key));
  }

  @PostMapping("/export-batches")
  @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
  public ApiResponse<Batch> export(
      @RequestBody ExportBatch input,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    return ApiResponse.success(service.export(actors.resolve(http), input, key));
  }

  @GetMapping("/{kind:interview|export}-batches/{id}")
  public ApiResponse<Batch> get(
      @PathVariable String kind, @PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.get(actors.resolve(http), id, kind));
  }
}
