package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrWorkbenchContracts.Workbench;
import com.aiep.aihub.application.hr.HrWorkbenchService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

/** 只读工作台，不在读取时触发任何AI生成。 */
@RestController
@RequestMapping("/api/hr/workbench")
public class HrWorkbenchController {
  private final HrWorkbenchService service;
  private final HrActorResolver actors;

  public HrWorkbenchController(HrWorkbenchService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @GetMapping
  public ApiResponse<Workbench> get(HttpServletRequest request) {
    return ApiResponse.success(service.get(actors.resolve(request)));
  }
}
