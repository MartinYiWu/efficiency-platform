package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.application.hr.HrInterviewExportService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** 下载均为私有、不可缓存、一次授权，不发布公共对象URL。 */
@RestController
@RequestMapping("/api/hr")
public class HrInterviewExportController {
  private final HrInterviewExportService service;
  private final HrActorResolver actors;

  public HrInterviewExportController(HrInterviewExportService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/exports")
  public ApiResponse<ExportView> create(
      @RequestBody ExportRequest request, HttpServletRequest http) {
    return ApiResponse.success(service.create(actors.resolve(http), request));
  }

  @GetMapping("/exports/{id}")
  public ApiResponse<ExportView> get(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(service.get(actors.resolve(http), id));
  }

  @GetMapping("/downloads/{grant}")
  public ResponseEntity<byte[]> download(@PathVariable String grant, HttpServletRequest http) {
    var actor = actors.resolve(http);
    String format = service.format(actor, grant);
    return ResponseEntity.ok()
        .header("Cache-Control", "no-store")
        .header(
            "Content-Disposition",
            "attachment; filename=interview-guide." + (format.equals("PDF") ? "pdf" : "docx"))
        .contentType(
            MediaType.parseMediaType(
                format.equals("PDF")
                    ? "application/pdf"
                    : "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        .body(service.download(actor, grant));
  }
}
