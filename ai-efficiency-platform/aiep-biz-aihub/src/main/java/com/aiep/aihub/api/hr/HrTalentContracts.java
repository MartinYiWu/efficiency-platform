package com.aiep.aihub.api.hr;

import java.time.Instant;
import java.util.List;

/** 人才查询只投影当前授权来源，不扩大合并后的权限。 */
public final class HrTalentContracts {
  private HrTalentContracts() {}

  public record TalentSummary(
      String candidateId,
      String name,
      String education,
      Integer experienceMonths,
      List<String> skills,
      Instant updatedAt,
      Instant expiresAt,
      boolean olderThan30Days,
      boolean expiringWithin30Days,
      String snippet,
      Double retrievalRelevance) {}

  public record SearchFilter(
      String query,
      String skill,
      String education,
      Integer minimumExperienceMonths,
      Integer maximumExperienceMonths,
      String excludeMatchedPositionId,
      Long dictionaryVersion) {}

  public record TalentPage(List<TalentSummary> items, long total, int page, int pageSize) {}

  public record SourceView(
      String candidateId,
      String departmentId,
      HrCandidateContracts.Facts facts,
      Instant expiresAt,
      String consentPolicyId,
      long candidateVersion) {}

  public record FactVersion(
      String snapshotId,
      String candidateId,
      String resumeVersionId,
      long version,
      Instant createdAt) {}

  public record MatchingHistory(
      String resultId,
      String candidateId,
      String positionId,
      String configVersion,
      String businessStatus,
      String status,
      Instant createdAt) {}

  public record TalentProfile(
      String candidateId,
      List<SourceView> sources,
      List<HrInterviewContracts.InterviewSet> interviewSets,
      String mergeId,
      Instant revocableUntil,
      Long mergeVersion,
      List<FactVersion> factVersions,
      List<MatchingHistory> matchingHistory) {
    public TalentProfile(
        String candidateId,
        List<SourceView> sources,
        List<HrInterviewContracts.InterviewSet> interviewSets,
        String mergeId,
        Instant revocableUntil,
        Long mergeVersion) {
      this(
          candidateId,
          sources,
          interviewSets,
          mergeId,
          revocableUntil,
          mergeVersion,
          List.of(),
          List.of());
    }
  }

  public record MergeRequest(
      String primaryCandidateId, List<String> sourceCandidateIds, String reason) {}

  public record MergeView(
      String id,
      String primaryCandidateId,
      List<String> sourceCandidateIds,
      String status,
      Instant createdAt,
      Instant revocableUntil,
      long version) {}

  public record Revocation(long expectedVersion, String reason) {}

  public record ContactRequest(String reason) {}

  public record ContactGrant(String id, Instant expiresAt) {}

  public record ContactView(String candidateId, String phone, String email) {}

  public record DeleteRequest(long expectedVersion, boolean confirmed, String reason) {}

  public record DeletionJob(
      String id,
      String candidateId,
      String status,
      String step,
      int attempts,
      Instant nextAttemptAt,
      Instant createdAt,
      boolean alert,
      String failureCode) {}

  public record AuditEvent(
      String id,
      String action,
      String actorId,
      String subjectRef,
      String departmentId,
      Instant occurredAt) {}

  public record AuditPage(List<AuditEvent> items, long total, int page, int pageSize) {}

  public record RetentionExtension(
      long expectedVersion, Instant expiresAt, String legalBasis, String policyVersion) {}
}
