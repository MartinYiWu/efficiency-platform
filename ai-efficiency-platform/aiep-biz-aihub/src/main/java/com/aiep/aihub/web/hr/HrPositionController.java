package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.HrPositionService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

/** 岗位配置HTTP边界；身份来自服务端解析，发布不接受浏览器自报规则版本所有者。 */
@RestController
@RequestMapping("/api/hr")
public class HrPositionController {
  private final HrPositionService positions;
  private final HrActorResolver actors;

  public HrPositionController(HrPositionService positions, HrActorResolver actors) {
    this.positions = positions;
    this.actors = actors;
  }

  @GetMapping("/session")
  public ApiResponse<HrActor> session(HttpServletRequest request) {
    return ApiResponse.success(actors.resolve(request));
  }

  @GetMapping("/positions")
  public ApiResponse<Page<Position>> list(
      HttpServletRequest request,
      @RequestParam(required = false) String keyword,
      @RequestParam(required = false) String family,
      @RequestParam(required = false) String status,
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int pageSize) {
    return ApiResponse.success(
        positions.list(actors.resolve(request), keyword, family, status, page, pageSize));
  }

  @PostMapping("/positions")
  @ResponseStatus(HttpStatus.CREATED)
  public ApiResponse<Position> create(
      HttpServletRequest request, @RequestBody CreatePosition input) {
    return ApiResponse.success(positions.create(actors.resolve(request), input));
  }

  @GetMapping("/positions/{id}")
  public ApiResponse<Position> get(HttpServletRequest request, @PathVariable String id) {
    return ApiResponse.success(positions.get(actors.resolve(request), id));
  }

  @GetMapping("/positions/{id}/draft")
  public ApiResponse<Draft> draft(HttpServletRequest request, @PathVariable String id) {
    return ApiResponse.success(positions.draft(actors.resolve(request), id));
  }

  @PutMapping("/positions/{id}/draft")
  public ApiResponse<Draft> save(
      HttpServletRequest request, @PathVariable String id, @RequestBody Draft input) {
    return ApiResponse.success(positions.save(actors.resolve(request), id, input));
  }

  @PostMapping("/positions/{id}/config-versions")
  public ApiResponse<ConfigVersion> publish(
      HttpServletRequest request, @PathVariable String id, @RequestBody Publish input) {
    return ApiResponse.success(
        positions.publish(actors.resolve(request), id, input.expectedVersion()));
  }

  @GetMapping("/positions/{id}/config-versions/{version}")
  public ApiResponse<ConfigVersion> config(
      HttpServletRequest request, @PathVariable String id, @PathVariable String version) {
    return ApiResponse.success(positions.config(actors.resolve(request), id, version));
  }

  @GetMapping("/positions/{id}/config-versions")
  public ApiResponse<java.util.List<ConfigVersion>> versions(
      @PathVariable String id, HttpServletRequest request) {
    return ApiResponse.success(positions.versions(actors.resolve(request), id));
  }

  @GetMapping("/positions/{id}/config-diff")
  public ApiResponse<HrPositionService.Difference> diff(
      @PathVariable String id,
      @RequestParam String from,
      @RequestParam String to,
      HttpServletRequest request) {
    return ApiResponse.success(positions.diff(actors.resolve(request), id, from, to));
  }

  @PostMapping("/positions/{id}/disable")
  public ApiResponse<Position> disable(
      HttpServletRequest request, @PathVariable String id, @RequestBody Publish input) {
    return ApiResponse.success(
        positions.disable(actors.resolve(request), id, input.expectedVersion()));
  }
}
