package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrJdDraftContracts.*;
import com.aiep.aihub.application.hr.HrJdDraftService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

/** JD原句候选须显式逐项采用，生成不直接更新岗位。 */
@RestController
@RequestMapping("/api/hr/positions/{positionId}/jd-drafts")
public class HrJdDraftController {
  private final HrJdDraftService service;
  private final HrActorResolver actors;

  public HrJdDraftController(HrJdDraftService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping
  public ApiResponse<JdDraft> generate(
      HttpServletRequest r, @PathVariable String positionId, @RequestBody Generate input) {
    return ApiResponse.success(service.generate(actors.resolve(r), positionId, input));
  }

  @PostMapping("/file")
  public ApiResponse<JdDraft> file(
      HttpServletRequest r,
      @PathVariable String positionId,
      @RequestParam long expectedPositionVersion,
      @RequestPart org.springframework.web.multipart.MultipartFile file) {
    return ApiResponse.success(
        service.generateFile(actors.resolve(r), positionId, expectedPositionVersion, file));
  }

  @GetMapping("/{id}")
  public ApiResponse<JdDraft> get(
      HttpServletRequest r, @PathVariable String positionId, @PathVariable String id) {
    return ApiResponse.success(service.get(actors.resolve(r), positionId, id));
  }

  @PostMapping("/{id}/adopt")
  public ApiResponse<JdDraft> adopt(
      HttpServletRequest r,
      @PathVariable String positionId,
      @PathVariable String id,
      @RequestBody Adopt input) {
    return ApiResponse.success(service.adopt(actors.resolve(r), positionId, id, input));
  }
}
