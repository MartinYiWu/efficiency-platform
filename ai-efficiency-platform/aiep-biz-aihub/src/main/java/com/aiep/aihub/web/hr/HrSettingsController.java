package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrSettingsContracts.*;
import com.aiep.aihub.application.hr.HrSettingsService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.*;

/** 全局配置草稿、发布和无正文审计入口。 */
@RestController
@RequestMapping("/api/hr")
public class HrSettingsController {
  private final HrSettingsService service;
  private final HrActorResolver actors;

  public HrSettingsController(HrSettingsService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @GetMapping(value = "/settings", params = "departmentId")
  public ApiResponse<Settings> get(HttpServletRequest r, @RequestParam String departmentId) {
    return ApiResponse.success(service.get(actors.resolve(r), departmentId));
  }

  @PutMapping("/settings")
  public ApiResponse<Settings> save(HttpServletRequest r, @RequestBody SaveSettings input) {
    return ApiResponse.success(service.save(actors.resolve(r), input));
  }

  @PostMapping("/settings/publish")
  public ApiResponse<Settings> publish(HttpServletRequest r, @RequestBody Publish input) {
    return ApiResponse.success(service.publish(actors.resolve(r), input));
  }

  @GetMapping("/settings/versions")
  public ApiResponse<List<Settings>> versions(
      HttpServletRequest r, @RequestParam String departmentId) {
    return ApiResponse.success(service.versions(actors.resolve(r), departmentId));
  }

  @GetMapping("/configuration-audit")
  public ApiResponse<List<Audit>> audit(
      HttpServletRequest r, @RequestParam(required = false) String departmentId) {
    return ApiResponse.success(service.audits(actors.resolve(r), departmentId));
  }
}
