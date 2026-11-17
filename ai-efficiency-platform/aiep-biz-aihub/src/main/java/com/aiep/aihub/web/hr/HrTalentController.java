package com.aiep.aihub.web.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.platformcore.api.ApiResponse;
import jakarta.servlet.http.*;
import org.springframework.web.bind.annotation.*;

/** 人才/来源/隐私操作均由服务层按当前身份与授权核验。 */
@RestController
@RequestMapping("/api/hr")
public class HrTalentController {
  private final HrActorResolver actors;
  private final HrTalentSearchService talent;
  private final HrCandidateMergeService merges;
  private final HrContactService contacts;
  private final HrDeletionService deletion;
  private final HrAuditService audits;
  private final HrInterviewService interviews;
  private final HrRetentionService retention;

  public HrTalentController(
      HrActorResolver actors,
      HrTalentSearchService talent,
      HrCandidateMergeService merges,
      HrContactService contacts,
      HrDeletionService deletion,
      HrAuditService audits,
      HrInterviewService interviews,
      HrRetentionService retention) {
    this.actors = actors;
    this.talent = talent;
    this.merges = merges;
    this.contacts = contacts;
    this.deletion = deletion;
    this.audits = audits;
    this.interviews = interviews;
    this.retention = retention;
  }

  @GetMapping("/candidates")
  public ApiResponse<TalentPage> search(
      @RequestParam(defaultValue = "") String query,
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int pageSize,
      @RequestParam(required = false) String skill,
      @RequestParam(required = false) String education,
      @RequestParam(required = false) Integer minimumExperienceMonths,
      @RequestParam(required = false) Integer maximumExperienceMonths,
      @RequestParam(required = false) String excludeMatchedPositionId,
      @RequestParam(required = false) Long dictionaryVersion,
      HttpServletRequest http) {
    return ApiResponse.success(
        talent.search(
            actors.resolve(http),
            new SearchFilter(
                query,
                skill,
                education,
                minimumExperienceMonths,
                maximumExperienceMonths,
                excludeMatchedPositionId,
                dictionaryVersion),
            page,
            pageSize));
  }

  @GetMapping("/candidates/{id}")
  public ApiResponse<TalentProfile> profile(@PathVariable String id, HttpServletRequest http) {
    var actor = actors.resolve(http);
    var p = talent.profile(actor, id);
    return ApiResponse.success(
        new TalentProfile(
            p.candidateId(),
            p.sources(),
            actor.permissions().contains("hr:interview:read")
                ? interviews.list(actor, p.sources().getFirst().candidateId())
                : java.util.List.of(),
            p.mergeId(),
            p.revocableUntil(),
            p.mergeVersion(),
            p.factVersions(),
            p.matchingHistory()));
  }

  @PostMapping("/candidate-merges")
  public ApiResponse<MergeView> merge(
      @RequestBody MergeRequest request,
      @RequestHeader("Idempotency-Key") String key,
      HttpServletRequest http) {
    return ApiResponse.success(merges.merge(actors.resolve(http), request, key));
  }

  @PostMapping("/candidate-merges/{id}/revocations")
  public ApiResponse<MergeView> revoke(
      @PathVariable String id, @RequestBody Revocation request, HttpServletRequest http) {
    return ApiResponse.success(merges.revoke(actors.resolve(http), id, request));
  }

  @PostMapping("/candidates/{id}/contact-grants")
  public ApiResponse<ContactGrant> grant(
      @PathVariable String id,
      @RequestBody ContactRequest request,
      HttpServletRequest http,
      HttpServletResponse response) {
    response.setHeader("Cache-Control", "no-store");
    return ApiResponse.success(contacts.grant(actors.resolve(http), id, request));
  }

  @GetMapping("/contact-grants/{id}")
  public ApiResponse<ContactView> contact(
      @PathVariable String id, HttpServletRequest http, HttpServletResponse response) {
    response.setHeader("Cache-Control", "no-store");
    return ApiResponse.success(contacts.read(actors.resolve(http), id));
  }

  @PostMapping("/candidates/{id}/deletions")
  public ApiResponse<DeletionJob> delete(
      @PathVariable String id, @RequestBody DeleteRequest request, HttpServletRequest http) {
    return ApiResponse.success(deletion.delete(actors.resolve(http), id, request));
  }

  @GetMapping("/deletion-jobs/{id}")
  public ApiResponse<DeletionJob> job(@PathVariable String id, HttpServletRequest http) {
    return ApiResponse.success(deletion.get(actors.resolve(http), id));
  }

  @PostMapping("/candidates/{id}/retention-extensions")
  public ApiResponse<Void> extend(
      @PathVariable String id, @RequestBody RetentionExtension request, HttpServletRequest http) {
    retention.extend(actors.resolve(http), id, request);
    return ApiResponse.success(null);
  }

  @GetMapping("/audit-events")
  public ApiResponse<AuditPage> audit(
      @RequestParam(defaultValue = "1") int page,
      @RequestParam(defaultValue = "20") int pageSize,
      HttpServletRequest http) {
    return ApiResponse.success(audits.list(actors.resolve(http), page, pageSize));
  }
}
