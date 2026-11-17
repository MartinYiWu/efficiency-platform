package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.HrMatchingService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/hr")
public class HrMatchingController {
  @GetMapping("/matching-results/{id}/configuration-snapshot") public ApiResponse<com.aiep.aihub.api.hr.HrPositionContracts.ConfigVersion> configurationSnapshot(@PathVariable String id,HttpServletRequest http){return ApiResponse.success(service.configurationSnapshot(actors.resolve(http),id));}
  @GetMapping("/matching-results/statistics")
  public ApiResponse<HrMatchingService.Statistics> statistics(
      @RequestParam String positionId,
      @RequestParam String configVersionId,
      HttpServletRequest http) {
    return ApiResponse.success(
        service.statistics(actors.resolve(http), positionId, configVersionId));
  }

  private final HrMatchingService service;
  private final HrActorResolver actors;
  private final com.aiep.aihub.application.hr.HrMatchingRunExecutor executor;

  public HrMatchingController(
      HrMatchingService service,
      HrActorResolver actors,
      com.aiep.aihub.application.hr.HrMatchingRunExecutor executor) {
    this.service = service;
    this.actors = actors;
    this.executor = executor;
  }

  @GetMapping({"/results/{id}", "/matching-results/{id}"})
  public ApiResponse<Matching> result(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.get(actors.resolve(http), id));
  }

  @GetMapping({"/results", "/matching-results"})
  public ApiResponse<com.aiep.aihub.api.hr.HrPositionContracts.Page<Matching>> list(
      @RequestParam(required = false) String positionId,
      @RequestParam(required = false) String candidateId,
      @RequestParam(required = false) String configVersionId,
      @RequestParam(required = false) String businessStatus,
      @RequestParam(required = false) String keyword,
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int pageSize,
      HttpServletRequest http) {
    return ApiResponse.success(
        service.list(
            actors.resolve(http),
            positionId,
            candidateId,
            configVersionId,
            businessStatus,
            keyword,
            page,
            pageSize));
  }

  @PostMapping("/matching-runs")
  @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
  public ApiResponse<RunResponse> match(
      @RequestBody MatchRequest request,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    var actor = actors.resolve(http);
    Run run = service.prepare(actor, request, key);
    executor.submit(actor, request, run);
    return ApiResponse.success(new RunResponse(run.id(), run.status()));
  }

  @PostMapping("/matching-runs/{id}/cancel")
  public ApiResponse<RunView> cancel(@PathVariable String id, HttpServletRequest http) {
    Run r = executor.cancel(actors.resolve(http), id);
    return ApiResponse.success(new RunView(r.id(), r.status(), r.resultId(), r.failureCode()));
  }

  @GetMapping("/matching-runs/{id}")
  public ApiResponse<RunView> run(@PathVariable String id, HttpServletRequest http) {
    Run r = service.run(actors.resolve(http), id);
    return ApiResponse.success(new RunView(r.id(), r.status(), r.resultId(), r.failureCode()));
  }

  @PostMapping("/recalculations")
  public ApiResponse<RunResponse> recalculateBatch(
      @RequestBody Recalculation request, HttpServletRequest http) {
    return ApiResponse.success(service.recalculate(actors.resolve(http), request));
  }

  @PostMapping("/recalculations/preview")
  public ApiResponse<com.aiep.aihub.api.hr.HrExecutionContracts.RecalculationPreview> preview(
      @RequestBody Recalculation request, HttpServletRequest http) {
    return ApiResponse.success(service.preview(actors.resolve(http), request));
  }

  @PostMapping("/results/{id}/recalculations")
  public ApiResponse<Matching> recalculate(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.recalculate(actors.resolve(http), id));
  }

  @PostMapping({"/matching-results/{id}/overrides", "/results/{id}/overrides"})
  public ApiResponse<Matching> override(
      @PathVariable String id, @RequestBody OverrideRequest request, HttpServletRequest http) {
    return ApiResponse.success(service.override(actors.resolve(http), id, request));
  }

  @PostMapping({
    "/matching-results/{id}/override-revocations",
    "/results/{id}/override-revocations"
  })
  public ApiResponse<Matching> revokeOverride(
      @PathVariable String id,
      @RequestBody RevokeOverrideRequest request,
      HttpServletRequest http) {
    return ApiResponse.success(service.revokeOverride(actors.resolve(http), id, request));
  }
}
