package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.DistinctConfirmation;
import com.aiep.aihub.application.hr.HrSpecialMarksService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

/** 不同人确认绑定双方事实版本；不自动合并或扩大授权。 */
@RestController
@RequestMapping("/api/hr/candidates")
public class HrSpecialMarksController {
  private final HrSpecialMarksService service;
  private final HrActorResolver actors;

  public HrSpecialMarksController(HrSpecialMarksService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/{id}/distinct-confirmations")
  public ApiResponse<Void> distinct(
      @PathVariable String id, @RequestBody DistinctConfirmation request, HttpServletRequest http) {
    service.confirmDistinct(actors.resolve(http), id, request);
    return ApiResponse.success(null);
  }
}
