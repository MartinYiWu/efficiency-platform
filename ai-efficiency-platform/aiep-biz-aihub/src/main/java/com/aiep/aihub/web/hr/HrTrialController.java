package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.application.hr.HrTrialService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.*;

/** Sandbox只读恢复不再发起评估，独立标注后返回系统对照。 */
@RestController
@RequestMapping("/api/hr/trials")
public class HrTrialController {
  private final HrTrialService service;
  private final HrActorResolver actors;

  public HrTrialController(HrTrialService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping
  public ApiResponse<Trial> create(HttpServletRequest r, @RequestBody Create input) {
    return ApiResponse.success(service.create(actors.resolve(r), input));
  }

  @GetMapping
  public ApiResponse<List<Trial>> list(HttpServletRequest r, @RequestParam String positionId) {
    return ApiResponse.success(service.list(actors.resolve(r), positionId));
  }

  @GetMapping("/{id}")
  public ApiResponse<Trial> get(HttpServletRequest r, @PathVariable String id) {
    return ApiResponse.success(service.get(actors.resolve(r), id));
  }

  @PostMapping("/{id}/execution-plan")
  public ApiResponse<ExecutionPlan> plan(
      HttpServletRequest r, @PathVariable String id, @RequestBody PlanRequest input) {
    return ApiResponse.success(service.plan(actors.resolve(r), id, input));
  }

  @GetMapping("/{id}/execution-plan")
  public ApiResponse<ExecutionPlan> plan(HttpServletRequest r, @PathVariable String id) {
    return ApiResponse.success(service.executionPlan(actors.resolve(r), id));
  }

  @PostMapping("/{id}/execute")
  public ApiResponse<Trial> execute(
      HttpServletRequest r, @PathVariable String id, @RequestBody ExecuteRequest input) {
    return ApiResponse.success(service.execute(actors.resolve(r), id, input));
  }

  @PostMapping("/{id}/labels")
  public ApiResponse<Trial> label(
      HttpServletRequest r, @PathVariable String id, @RequestBody Labels input) {
    return ApiResponse.success(service.label(actors.resolve(r), id, input));
  }
}
