package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.HrCandidateService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/hr/candidates")
public class HrCandidateController {
  private final HrCandidateService service;
  private final HrActorResolver actors;

  public HrCandidateController(HrCandidateService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping
  public ApiResponse<Facts> create(@RequestBody ImportResume request, HttpServletRequest http) {
    actors.resolve(http);
    throw new com.aiep.aihub.application.hr.HrBusinessException(
        "HR_BATCH_REQUIRED", "请通过授权简历批次上传材料", 503);
  }

  @GetMapping("/{id}/facts")
  public ApiResponse<Facts> facts(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.facts(actors.resolve(http), id));
  }

  @GetMapping("/{id}/fact-history")
  public org.springframework.http.ResponseEntity<ApiResponse<java.util.List<Facts>>> history(
      @PathVariable String id, HttpServletRequest http) {
    return org.springframework.http.ResponseEntity.ok()
        .cacheControl(org.springframework.http.CacheControl.noStore())
        .body(ApiResponse.success(service.history(actors.resolve(http), id)));
  }

  @PostMapping("/{id}/skips")
  public ApiResponse<Facts> skip(
      @PathVariable String id, @RequestBody Skip input, HttpServletRequest http) {
    return ApiResponse.success(service.skip(actors.resolve(http), id, input));
  }

  @PostMapping("/{id}/corrections")
  public ApiResponse<Facts> correct(
      @PathVariable String id, @RequestBody Corrections request, HttpServletRequest http) {
    return ApiResponse.success(service.correct(actors.resolve(http), id, request));
  }

  @PostMapping("/{id}/confirmations")
  public ApiResponse<Facts> confirm(
      @PathVariable String id, @RequestBody Confirmations request, HttpServletRequest http) {
    return ApiResponse.success(service.confirm(actors.resolve(http), id, request));
  }

  @PostMapping("/{id}/structured-corrections")
  public ApiResponse<Facts> correctStructured(
      @PathVariable String id,
      @RequestBody StructuredCorrections request,
      HttpServletRequest http) {
    return ApiResponse.success(service.correctStructured(actors.resolve(http), id, request));
  }
}
