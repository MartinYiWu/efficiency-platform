package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrDictionaryContracts.*;
import com.aiep.aihub.api.hr.HrSettingsContracts.*;
import com.aiep.aihub.application.hr.HrDictionaryFileReader;
import com.aiep.aihub.application.hr.HrDictionaryService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/** 词典CSV/XLSX先预检，采用是独立原子事务。 */
@RestController
@RequestMapping("/api/hr/dictionaries")
public class HrDictionaryController {
  private final HrDictionaryService service;
  private final HrActorResolver actors;

  public HrDictionaryController(HrDictionaryService service, HrActorResolver actors) {
    this.service = service;
    this.actors = actors;
  }

  @GetMapping
  public ApiResponse<Dictionary> get(HttpServletRequest r, @RequestParam String departmentId) {
    return ApiResponse.success(service.get(actors.resolve(r), departmentId));
  }

  @PutMapping
  public ApiResponse<Dictionary> save(HttpServletRequest r, @RequestBody Save input) {
    return ApiResponse.success(service.save(actors.resolve(r), input));
  }

  @PostMapping("/publish")
  public ApiResponse<Dictionary> publish(HttpServletRequest r, @RequestBody Publish input) {
    return ApiResponse.success(
        service.publish(actors.resolve(r), input.departmentId(), input.expectedVersion()));
  }

  @GetMapping("/versions")
  public ApiResponse<List<Dictionary>> versions(
      HttpServletRequest r, @RequestParam String departmentId) {
    return ApiResponse.success(service.versions(actors.resolve(r), departmentId));
  }

  @PostMapping("/import-preflight")
  public ApiResponse<ImportPreview> preflight(HttpServletRequest r, @RequestBody Save input) {
    return ApiResponse.success(service.preflight(actors.resolve(r), input));
  }

  @PostMapping("/import-file")
  public ApiResponse<ImportPreview> file(
      HttpServletRequest r,
      @RequestParam String departmentId,
      @RequestParam long expectedVersion,
      @RequestPart MultipartFile file) {
    var actor = actors.resolve(r);
    com.aiep.aihub.application.hr.HrAccessPolicy.require(actor, "hr:config:edit");
    com.aiep.aihub.application.hr.HrAccessPolicy.department(actor, departmentId);
    return ApiResponse.success(
        service.preflight(
            actor, new Save(departmentId, expectedVersion, HrDictionaryFileReader.read(file))));
  }

  @PostMapping("/imports/{id}/adopt")
  public ApiResponse<Dictionary> adopt(
      HttpServletRequest r, @PathVariable String id, @RequestBody Version input) {
    return ApiResponse.success(service.adopt(actors.resolve(r), id, input.expectedVersion()));
  }

  @PostMapping("/normalize")
  public ApiResponse<Normalized> normalize(HttpServletRequest r, @RequestBody Normalize input) {
    return ApiResponse.success(service.normalize(actors.resolve(r), input));
  }

  @GetMapping("/export")
  public ResponseEntity<byte[]> export(HttpServletRequest r, @RequestParam String departmentId) {
    return ResponseEntity.ok()
        .contentType(new MediaType("text", "csv", StandardCharsets.UTF_8))
        .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=hr-dictionary.csv")
        .body(service.export(actors.resolve(r), departmentId).getBytes(StandardCharsets.UTF_8));
  }
}
