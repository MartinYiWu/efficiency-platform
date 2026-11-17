package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import org.springframework.web.bind.annotation.*;

/** 招聘人员题集与面试官独立安全入口。 */
@RestController
@RequestMapping("/api/hr")
public class HrInterviewController {
  private final HrActorResolver actors;
  private final HrInterviewService interviews;
  private final HrInterviewAssignmentService assignments;

  public HrInterviewController(
      HrActorResolver actors,
      HrInterviewService interviews,
      HrInterviewAssignmentService assignments) {
    this.actors = actors;
    this.interviews = interviews;
    this.assignments = assignments;
  }

  @PostMapping("/interview-sets")
  public ApiResponse<InterviewSet> generate(
      @RequestBody GenerateRequest request,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    return ApiResponse.success(interviews.generate(actors.resolve(http), request, key));
  }

  @GetMapping("/interview-sets")
  public ApiResponse<List<InterviewSet>> list(
      @RequestParam String candidateId, HttpServletRequest http) {
    return ApiResponse.success(interviews.list(actors.resolve(http), candidateId));
  }

  @GetMapping("/interview-sets/{id}")
  public ApiResponse<InterviewSet> get(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(interviews.get(actors.resolve(http), id, null));
  }

  @PutMapping("/interview-sets/{id}")
  public ApiResponse<InterviewSet> edit(
      @PathVariable String id, @RequestBody EditRequest request, HttpServletRequest http) {
    return ApiResponse.success(interviews.edit(actors.resolve(http), id, request));
  }

  @PostMapping("/interview-sets/{id}/questions/{questionId}/regenerations")
  public ApiResponse<InterviewSet> regenerate(
      @PathVariable String id,
      @PathVariable String questionId,
      @RequestBody RegenerationRequest request,
      HttpServletRequest http) {
    return ApiResponse.success(
        interviews.regenerate(actors.resolve(http), id, questionId, request));
  }

  @PostMapping("/interview-assignments")
  public ApiResponse<Assignment> assign(
      @RequestBody AssignRequest request, HttpServletRequest http) {
    return ApiResponse.success(assignments.assign(actors.resolve(http), request));
  }

  @GetMapping("/interview-assignments/{id}/view")
  public ApiResponse<InterviewGuide> view(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(assignments.assigned(actors.resolve(http), id));
  }

  @PostMapping("/interview-assignments/{id}/revocations")
  public ApiResponse<Void> revoke(
      @PathVariable String id,
      @RequestBody com.aiep.aihub.api.hr.HrTalentContracts.ContactRequest request,
      HttpServletRequest http) {
    assignments.revoke(actors.resolve(http), id, request.reason());
    return ApiResponse.success(null);
  }

  @GetMapping("/interview-sets/{id}/preview")
  public ApiResponse<InterviewGuide> preview(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(assignments.preview(actors.resolve(http), id));
  }
}
