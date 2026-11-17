package com.aiep.aihub.web.hr;

import com.aiep.aihub.application.hr.HrEvidenceService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/hr")
public class HrEvidenceController {
  private final HrEvidenceService service;
  private final HrActorResolver actors;

  public HrEvidenceController(HrEvidenceService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @PostMapping("/candidates/{id}/original-grants")
  public ApiResponse<HrEvidenceService.Grant> grant(
      @PathVariable String id, HttpServletRequest request) {
    return ApiResponse.success(service.grant(actors.resolve(request), id));
  }

  @GetMapping("/original-grants/{id}")
  public ResponseEntity<byte[]> original(@PathVariable String id, HttpServletRequest request) {
    var original = service.read(actors.resolve(request), id);
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .header("X-Content-Type-Options", "nosniff")
        .header("Content-Security-Policy", "sandbox; default-src 'none'")
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment()
                .filename(original.filename(), java.nio.charset.StandardCharsets.UTF_8)
                .build()
                .toString())
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(original.content());
  }
}
