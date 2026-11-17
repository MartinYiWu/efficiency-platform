package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.application.hr.HrInterviewTemplateService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/** 面试模板草稿/不可变发布历史，与评分模板独立。 */
@RestController
@RequestMapping("/api/hr/interview-templates")
public class HrInterviewTemplateController {
  private final HrActorResolver actors;
  private final HrInterviewTemplateService service;

  public HrInterviewTemplateController(HrActorResolver actors, HrInterviewTemplateService service) {
    this.actors = actors;
    this.service = service;
  }

  @GetMapping
  public ApiResponse<List<Template>> list(HttpServletRequest http) {
    return ApiResponse.success(service.list(actors.resolve(http)));
  }

  @PostMapping
  public ApiResponse<Template> create(@RequestBody SaveTemplate request, HttpServletRequest http) {
    return ApiResponse.success(service.save(actors.resolve(http), null, request));
  }

  @PutMapping("/{id}")
  public ApiResponse<Template> edit(
      @PathVariable String id, @RequestBody SaveTemplate request, HttpServletRequest http) {
    return ApiResponse.success(service.save(actors.resolve(http), id, request));
  }

  @PostMapping("/{id}/versions")
  public ApiResponse<Template> publish(
      @PathVariable String id,
      @RequestBody com.aiep.aihub.api.hr.HrPositionContracts.Publish request,
      HttpServletRequest http) {
    return ApiResponse.success(
        service.publish(actors.resolve(http), id, request.expectedVersion()));
  }

  @GetMapping("/{id}/versions")
  public ApiResponse<List<Template>> versions(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.versions(actors.resolve(http), id));
  }
}
