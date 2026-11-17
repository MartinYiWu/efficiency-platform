package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.Position;
import com.aiep.aihub.api.hr.HrSettingsContracts.Version;
import com.aiep.aihub.api.hr.HrTemplateContracts.*;
import com.aiep.aihub.application.hr.HrTemplateService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.*;

/** 模板复制和不可变版本HTTP入口。 */
@RestController
@RequestMapping("/api/hr/templates")
public class HrTemplateController {
  private final HrTemplateService service;
  private final HrActorResolver actors;

  public HrTemplateController(HrTemplateService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @GetMapping
  public ApiResponse<List<Template>> list(
      HttpServletRequest r,
      @RequestParam(required = false) String departmentId,
      @RequestParam(required = false) String family) {
    return ApiResponse.success(service.list(actors.resolve(r), departmentId, family));
  }

  @PostMapping
  public ApiResponse<Template> create(HttpServletRequest r, @RequestBody Create input) {
    return ApiResponse.success(service.create(actors.resolve(r), input));
  }

  @PostMapping("/from-position")
  public ApiResponse<Template> fromPosition(HttpServletRequest r, @RequestBody SavePosition input) {
    return ApiResponse.success(service.fromPosition(actors.resolve(r), input));
  }

  @GetMapping("/{id}")
  public ApiResponse<Template> get(HttpServletRequest r, @PathVariable String id) {
    return ApiResponse.success(service.get(actors.resolve(r), id));
  }

  @PutMapping("/{id}")
  public ApiResponse<Template> edit(
      HttpServletRequest r, @PathVariable String id, @RequestBody Edit input) {
    return ApiResponse.success(service.edit(actors.resolve(r), id, input));
  }

  @PostMapping("/{id}/publish")
  public ApiResponse<Template> publish(
      HttpServletRequest r, @PathVariable String id, @RequestBody Version input) {
    return ApiResponse.success(service.publish(actors.resolve(r), id, input.expectedVersion()));
  }

  @PostMapping("/{id}/validate")
  public ApiResponse<Template> validateTrial(
      HttpServletRequest r, @PathVariable String id, @RequestBody Validate input) {
    return ApiResponse.success(service.validateTrial(actors.resolve(r), id, input));
  }

  @PostMapping("/{id}/copy")
  public ApiResponse<Template> copy(
      HttpServletRequest r, @PathVariable String id, @RequestBody Copy input) {
    return ApiResponse.success(service.copy(actors.resolve(r), id, input));
  }

  @PostMapping("/{id}/positions")
  public ApiResponse<Position> position(
      HttpServletRequest r, @PathVariable String id, @RequestBody CreateFromTemplate input) {
    return ApiResponse.success(service.position(actors.resolve(r), id, input));
  }

  @GetMapping("/{id}/versions")
  public ApiResponse<List<Template>> versions(HttpServletRequest r, @PathVariable String id) {
    return ApiResponse.success(service.versions(actors.resolve(r), id));
  }
}
