package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.Draft;
import com.aiep.aihub.application.hr.HrSoftRuleDraftService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

/** 条件转换仅保存未发布草稿，不修改历史结果也不发送模型。 */
@RestController
@RequestMapping("/api/hr/matching-results")
public class HrSoftRuleDraftController {
  private final HrSoftRuleDraftService service;
  private final HrActorResolver actors;

  public HrSoftRuleDraftController(HrSoftRuleDraftService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/{id}/soft-rule-drafts")
  public ApiResponse<Draft> create(
      @PathVariable String id,
      @RequestBody HrSoftRuleDraftService.Request request,
      HttpServletRequest http) {
    return ApiResponse.success(service.create(actors.resolve(http), id, request));
  }
}
