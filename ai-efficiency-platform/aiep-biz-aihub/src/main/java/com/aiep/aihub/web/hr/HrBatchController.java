package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.HrBatchContracts.*;
import com.aiep.aihub.application.hr.HrBatchExecutor;
import com.aiep.aihub.application.hr.HrBatchService;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/** 上传先冻结授权及策略，单条材料失败不写成候选人匹配失败。 */
@RestController
@RequestMapping("/api/hr")
public class HrBatchController {
  private final HrBatchService service;
  private final HrBatchExecutor executor;
  private final HrActorResolver actors;
  private com.aiep.aihub.application.hr.HrArchiveUploadService uploads;

  @org.springframework.beans.factory.annotation.Autowired
  public HrBatchController(
      HrBatchService service,
      HrBatchExecutor executor,
      HrActorResolver actors,
      com.aiep.aihub.application.hr.HrArchiveUploadService uploads) {
    this(service, executor, actors);
    this.uploads = uploads;
  }

  public HrBatchController(
      HrBatchService service, HrBatchExecutor executor, HrActorResolver actors) {
    this.service = service;
    this.executor = executor;
    this.actors = actors;
  }

  @GetMapping("/settings/upload-policy")
  public ApiResponse<UploadPolicy> policy(HttpServletRequest http) {
    return ApiResponse.success(service.uploadPolicy(actors.resolve(http)));
  }

  @GetMapping(value = "/settings", params = "!departmentId")
  public ApiResponse<Policy> settings(HttpServletRequest http) {
    var actor = actors.resolve(http);
    com.aiep.aihub.application.hr.HrAccessPolicy.require(actor, "hr:settings:read");
    return ApiResponse.success(service.policy(actor));
  }

  @PostMapping("/settings/versions")
  public ApiResponse<Policy> publish(HttpServletRequest http, @RequestBody Policy input) {
    return ApiResponse.success(service.publishPolicy(actors.resolve(http), input));
  }

  @PostMapping("/resume-batches")
  @ResponseStatus(HttpStatus.CREATED)
  public ApiResponse<Batch> create(
      HttpServletRequest http,
      @RequestHeader("Idempotency-Key") String key,
      @RequestBody CreateBatch input) {
    return ApiResponse.success(service.create(actors.resolve(http), input, key));
  }

  @GetMapping("/resume-batches/{id}")
  public ApiResponse<Batch> get(HttpServletRequest http, @PathVariable String id) {
    return ApiResponse.success(service.get(actors.resolve(http), id));
  }

  @PostMapping(
      value = "/resume-batches/{id}/uploads",
      consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
  public ApiResponse<BatchItem> upload(
      HttpServletRequest http, @PathVariable String id, @RequestPart("file") MultipartFile file)
      throws IOException {
    if (file.getSize() > 100L * 1024 * 1024)
      throw new IllegalArgumentException("HR_FILE_TOO_LARGE");
    return ApiResponse.success(
        uploads.upload(actors.resolve(http), id, file.getOriginalFilename(), file.getBytes()));
  }

  @PostMapping(value = "/resume-batches/{id}/uploads", consumes = MediaType.APPLICATION_JSON_VALUE)
  public ApiResponse<BatchItem> text(
      HttpServletRequest http, @PathVariable String id, @RequestBody TextUpload input) {
    if (input.text() == null
        || input.text().isBlank()
        || input.text().codePointCount(0, input.text().length()) > 50000)
      throw new IllegalArgumentException("HR_FILE_TEXT_LIMIT");
    return ApiResponse.success(
        service.upload(
            actors.resolve(http),
            id,
            input.filename() == null ? "粘贴简历.txt" : input.filename(),
            input.text().getBytes(StandardCharsets.UTF_8)));
  }

  @PostMapping("/resume-batches/{id}/start")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public ApiResponse<Batch> start(
      HttpServletRequest http, @PathVariable String id, @RequestBody Version input) {
    var actor = actors.resolve(http);
    Batch batch = service.start(actor, id, input.expectedVersion());
    executor.submit(actor, id);
    return ApiResponse.success(batch);
  }

  @PostMapping("/resume-batches/{id}/execution-plan")
  public ApiResponse<com.aiep.aihub.application.hr.HrBatchBudgetService.BudgetPlan> plan(
      @PathVariable String id, HttpServletRequest request) {
    return ApiResponse.success(service.executionPlan(actors.resolve(request), id));
  }

  @PostMapping("/resume-batches/{id}/cancel")
  public ApiResponse<Batch> cancel(HttpServletRequest http, @PathVariable String id) {
    var actor = actors.resolve(http);
    executor.cancel(actor, id);
    return ApiResponse.success(service.get(actor, id));
  }

  @PostMapping("/batch-items/{id}/cancel")
  public ApiResponse<BatchItem> cancelItem(HttpServletRequest http, @PathVariable String id) {
    return ApiResponse.success(service.cancelItem(actors.resolve(http), id));
  }

  @PostMapping("/candidates/{id}/continue")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public ApiResponse<com.aiep.aihub.api.hr.HrCandidateContracts.RunResponse> continueCandidate(
      HttpServletRequest http,
      @PathVariable String id,
      @RequestHeader("Idempotency-Key") String key,
      @RequestBody Version input) {
    return ApiResponse.success(
        service.continueCandidate(actors.resolve(http), id, input.expectedVersion(), key));
  }
}
