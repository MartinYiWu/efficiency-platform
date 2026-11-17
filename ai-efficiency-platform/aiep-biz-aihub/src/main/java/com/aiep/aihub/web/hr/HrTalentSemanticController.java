package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrTalentSemanticContracts.*;
import com.aiep.aihub.application.hr.HrTalentSemanticService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** 显式POST提交，读取GET不调用模型、不重建预算。 */
@RestController
@RequestMapping("/api/hr/talent-search-jobs")
public class HrTalentSemanticController {
  private final HrTalentSemanticService service;
  private final HrActorResolver actors;

  public HrTalentSemanticController(HrTalentSemanticService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping
  public ResponseEntity<ApiResponse<SearchJob>> create(
      @RequestBody SearchRequest request,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    return ResponseEntity.status(202)
        .body(ApiResponse.success(service.create(actors.resolve(http), request, key)));
  }

  @GetMapping("/{id}")
  public ApiResponse<SearchJob> get(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.get(actors.resolve(http), id));
  }
}
