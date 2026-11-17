package com.aiep.aihub.api.hr;

import java.util.List;

public final class HrCandidateContracts {
  private HrCandidateContracts() {}

  public record Block(
      String id,
      Integer page,
      String text,
      String section,
      List<Double> bbox,
      Integer paragraph,
      Double ocrQuality) {
    public Block(String id, Integer page, String text, String section) {
      this(id, page, text, section, null, null, null);
    }
  }

  public record Profile(
      String name, String education, Integer experienceMonths, String targetPosition) {}

  public record Field(
      String id,
      String label,
      String value,
      String status,
      String reason,
      List<String> evidenceIds) {}

  public record Skill(String name, String strength, int evidenceCount, List<String> evidenceIds) {}

  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record Evidence(String blockId, int start, int end, String quote) {}

  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record DateValue(String value, String precision, String sourceText) {}

  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record StructuredFact(
      String factId,
      String kind,
      String value,
      List<Evidence> evidence,
      String organization,
      String title,
      String degree,
      String major,
      DateValue startDate,
      DateValue endDate,
      Boolean ongoing,
      Boolean isInternship,
      Measurement measurement,
      String backgroundClaim) {
    public StructuredFact(
        String factId,
        String kind,
        String value,
        List<Evidence> evidence,
        String organization,
        String title,
        String degree,
        String major,
        DateValue startDate,
        DateValue endDate,
        Boolean ongoing,
        Boolean isInternship,
        Measurement measurement) {
      this(
          factId,
          kind,
          value,
          evidence,
          organization,
          title,
          degree,
          major,
          startDate,
          endDate,
          ongoing,
          isInternship,
          measurement,
          null);
    }

    public StructuredFact(
        String factId,
        String kind,
        String value,
        List<Evidence> evidence,
        String organization,
        String title,
        String degree,
        String major,
        DateValue startDate,
        DateValue endDate,
        Boolean ongoing,
        Boolean isInternship) {
      this(
          factId,
          kind,
          value,
          evidence,
          organization,
          title,
          degree,
          major,
          startDate,
          endDate,
          ongoing,
          isInternship,
          null);
    }
  }

  /** 同一项目的明确测量，禁止把不同项目的规模、角色和管理人数拼接。 */
  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record Measurement(
      String metric,
      String unit,
      java.math.BigDecimal value,
      String projectId,
      Integer roleLevel,
      Integer managedTeamSize) {}

  public record Facts(
      String candidateId,
      String resumeVersionId,
      String filename,
      int pageCount,
      Integer qualityScore,
      String status,
      Profile profile,
      List<Block> blocks,
      List<Field> fields,
      List<Skill> skills,
      int confirmedCount,
      int totalCount,
      long version,
      List<StructuredFact> structuredFacts,
      List<String> notApplicableGroups,
      List<FactNormalization> normalizations,
      Long dictionaryVersion) {
    public Facts(
        String candidateId,
        String resumeVersionId,
        String filename,
        int pageCount,
        Integer qualityScore,
        String status,
        Profile profile,
        List<Block> blocks,
        List<Field> fields,
        List<Skill> skills,
        int confirmedCount,
        int totalCount,
        long version,
        List<StructuredFact> structuredFacts,
        List<String> notApplicableGroups) {
      this(
          candidateId,
          resumeVersionId,
          filename,
          pageCount,
          qualityScore,
          status,
          profile,
          blocks,
          fields,
          skills,
          confirmedCount,
          totalCount,
          version,
          structuredFacts,
          notApplicableGroups,
          List.of(),
          null);
    }

    public Facts {
      normalizations = normalizations == null ? List.of() : List.copyOf(normalizations);
      structuredFacts = structuredFacts == null ? List.of() : List.copyOf(structuredFacts);
      notApplicableGroups =
          notApplicableGroups == null ? List.of() : List.copyOf(notApplicableGroups);
    }

    public Facts(
        String candidateId,
        String resumeVersionId,
        String filename,
        int pageCount,
        Integer qualityScore,
        String status,
        Profile profile,
        List<Block> blocks,
        List<Field> fields,
        List<Skill> skills,
        int confirmedCount,
        int totalCount,
        long version,
        List<StructuredFact> structuredFacts) {
      this(
          candidateId,
          resumeVersionId,
          filename,
          pageCount,
          qualityScore,
          status,
          profile,
          blocks,
          fields,
          skills,
          confirmedCount,
          totalCount,
          version,
          structuredFacts,
          List.of());
    }

    public Facts(
        String candidateId,
        String resumeVersionId,
        String filename,
        int pageCount,
        Integer qualityScore,
        String status,
        Profile profile,
        List<Block> blocks,
        List<Field> fields,
        List<Skill> skills,
        int confirmedCount,
        int totalCount,
        long version) {
      this(
          candidateId,
          resumeVersionId,
          filename,
          pageCount,
          qualityScore,
          status,
          profile,
          blocks,
          fields,
          skills,
          confirmedCount,
          totalCount,
          version,
          List.of());
    }
  }

  /** 原句与标准值并存；词典ID及版本冻结，不改写原始事实。 */
  public record FactNormalization(
      String factId,
      String category,
      String original,
      String standardId,
      String canonical,
      String status,
      long dictionaryVersion,
      int quality) {}

  public record Correction(String fieldId, String value, String reason) {}

  public record Corrections(
      long expectedVersion,
      @com.fasterxml.jackson.annotation.JsonAlias("corrections") List<Correction> changes) {}

  public record Confirmations(
      long expectedVersion,
      List<String> fieldIds,
      String reason,
      List<String> notApplicableGroups) {
    public Confirmations(long expectedVersion, List<String> fieldIds, String reason) {
      this(expectedVersion, fieldIds, reason, null);
    }
  }

  public record Skip(long expectedVersion, boolean confirmed, String reason) {}

  public record ImportResume(
      String departmentId,
      String filename,
      String contentBase64,
      boolean consentConfirmed,
      String consentVersion) {}

  public record Candidate(
      String id,
      String tenantId,
      String departmentId,
      String currentSnapshotId,
      long version,
      String consentPolicyId,
      java.time.Instant acquiredAt,
      java.time.Instant expiresAt,
      String status) {
    public Candidate(
        String id, String tenantId, String departmentId, String currentSnapshotId, long version) {
      this(
          id,
          tenantId,
          departmentId,
          currentSnapshotId,
          version,
          "synthetic-policy",
          java.time.Instant.now(),
          java.time.Instant.now().plusSeconds(86400),
          "ACTIVE");
    }
  }

  public record Snapshot(
      String id,
      String tenantId,
      String candidateId,
      String resumeVersionId,
      long version,
      String factsJson,
      String createdBy,
      String createdAt) {}

  public record RequirementView(
      String id, String label, String judgment, String quote, List<String> evidenceIds) {}

  public record DimensionView(
      String id,
      String label,
      java.math.BigDecimal score,
      int weight,
      java.math.BigDecimal evidenceCoverage,
      List<RequirementView> requirements) {}

  public record HardConditionView(
      String id,
      String label,
      String status,
      String expected,
      String actual,
      boolean overridable) {}

  public record OverrideView(
      String id,
      String conditionId,
      String reason,
      String actorId,
      String createdAt,
      String action,
      String revokedOverrideId) {}

  public record RunView(String runId, String status, String resultId, String failureCode) {}

  public record SpecialMark(String key, boolean active, boolean visible, String reason) {}

  public record DistinctConfirmation(
      String otherCandidateId, long expectedFactVersion, long otherFactVersion, String reason) {}

  public record Matching(
      String resultId,
      String candidateId,
      String candidateName,
      String positionId,
      String positionName,
      String factSnapshotId,
      String configVersion,
      String contextVersion,
      String semanticSnapshotId,
      String asOfDate,
      String businessStatus,
      String scoreStatus,
      java.math.BigDecimal totalScore,
      java.math.BigDecimal referenceScore,
      java.math.BigDecimal evidenceCoverage,
      String band,
      List<String> reasonCodes,
      List<DimensionView> dimensions,
      List<HardConditionView> hardConditions,
      List<OverrideView> overrides,
      String snapshotHash,
      String createdAt,
      String supersededBy,
      List<String> highlights,
      List<String> reviewPoints,
      List<Integer> thresholds,
      int pageCount,
      List<Block> blocks,
      Explanation explanation,
      List<SpecialMark> specialMarks) {
    public Matching {
      specialMarks = specialMarks == null ? List.of() : List.copyOf(specialMarks);
    }

    public Matching(
        String resultId,
        String candidateId,
        String candidateName,
        String positionId,
        String positionName,
        String factSnapshotId,
        String configVersion,
        String contextVersion,
        String semanticSnapshotId,
        String asOfDate,
        String businessStatus,
        String scoreStatus,
        java.math.BigDecimal totalScore,
        java.math.BigDecimal referenceScore,
        java.math.BigDecimal evidenceCoverage,
        String band,
        List<String> reasonCodes,
        List<DimensionView> dimensions,
        List<HardConditionView> hardConditions,
        List<OverrideView> overrides,
        String snapshotHash,
        String createdAt,
        String supersededBy,
        List<String> highlights,
        List<String> reviewPoints,
        List<Integer> thresholds,
        int pageCount,
        List<Block> blocks,
        Explanation explanation) {
      this(
          resultId,
          candidateId,
          candidateName,
          positionId,
          positionName,
          factSnapshotId,
          configVersion,
          contextVersion,
          semanticSnapshotId,
          asOfDate,
          businessStatus,
          scoreStatus,
          totalScore,
          referenceScore,
          evidenceCoverage,
          band,
          reasonCodes,
          dimensions,
          hardConditions,
          overrides,
          snapshotHash,
          createdAt,
          supersededBy,
          highlights,
          reviewPoints,
          thresholds,
          pageCount,
          blocks,
          explanation,
          List.of());
    }
  }

  public record MatchRequest(String candidateId, String positionId, long expectedVersion) {}

  public record Run(
      String id,
      String tenantId,
      String candidateId,
      String positionId,
      String status,
      String resultId,
      String failureCode,
      java.time.Instant createdAt,
      String inputJson,
      java.time.Instant deadlineAt,
      String idempotencyKey,
      String requestHash,
      String scopeRef) {}

  public record FrozenInput(
      MatchRequest request,
      Facts facts,
      String factSnapshotId,
      com.aiep.aihub.api.hr.HrPositionContracts.Position position,
      com.aiep.aihub.api.hr.HrPositionContracts.ConfigVersion config) {}

  public record SemanticSnapshot(
      String id,
      String tenantId,
      String candidateId,
      String factSnapshotId,
      String configJson,
      String assessmentsJson,
      String hardConditionsJson,
      String createdAt) {}

  public record ResultSnapshot(
      String id,
      String tenantId,
      String candidateId,
      String positionId,
      String factSnapshotId,
      String configVersion,
      String contextVersion,
      String semanticSnapshotId,
      String resultJson,
      String status,
      String supersededBy,
      String createdAt,
      String businessStatus,
      java.math.BigDecimal totalScore,
      java.math.BigDecimal evidenceCoverage,
      String band) {
    public ResultSnapshot(
        String id,
        String tenantId,
        String candidateId,
        String positionId,
        String factSnapshotId,
        String configVersion,
        String contextVersion,
        String semanticSnapshotId,
        String resultJson,
        String status,
        String supersededBy,
        String createdAt,
        String businessStatus) {
      this(
          id,
          tenantId,
          candidateId,
          positionId,
          factSnapshotId,
          configVersion,
          contextVersion,
          semanticSnapshotId,
          resultJson,
          status,
          supersededBy,
          createdAt,
          businessStatus,
          null,
          null,
          null);
    }
  }

  public record RecalculationWeights(
      int skills, int experience, int projects, int education, int bonus) {}

  public record Recalculation(
      String positionId,
      String sourceConfigVersion,
      List<String> resultIds,
      RecalculationWeights weights,
      List<Integer> thresholds,
      String mode,
      long expectedVersion,
      String previewHash) {
    public Recalculation(
        String positionId,
        String sourceConfigVersion,
        List<String> resultIds,
        RecalculationWeights weights,
        List<Integer> thresholds,
        String mode,
        long expectedVersion) {
      this(
          positionId,
          sourceConfigVersion,
          resultIds,
          weights,
          thresholds,
          mode,
          expectedVersion,
          null);
    }
  }

  public record RunResponse(String runId, String status) {}

  public record StructuredCorrection(
      String fieldId, StructuredFact fact, String reason, String humanSource) {
    public StructuredCorrection(String fieldId, StructuredFact fact, String reason) {
      this(fieldId, fact, reason, null);
    }
  }

  public record StructuredCorrections(long expectedVersion, List<StructuredCorrection> changes) {}

  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record SemanticAssessment(
      String requirementId, String status, String reason, List<Evidence> evidence) {}

  public record SemanticAssessments(
      List<com.aiep.aihub.domain.hr.HrAtomicAssessment> atomic, List<SemanticAssessment> source) {}

  @com.fasterxml.jackson.databind.annotation.JsonNaming(
      com.fasterxml.jackson.databind.PropertyNamingStrategies.SnakeCaseStrategy.class)
  public record ExplanationItem(
      String text, List<Evidence> evidence, List<String> requirementIds) {}

  public record Explanation(
      List<ExplanationItem> highlights,
      List<ExplanationItem> gaps,
      String status,
      List<ExplanationItem> verificationPoints,
      List<ExplanationItem> qualityNotes,
      String summary) {
    public Explanation(
        List<ExplanationItem> highlights, List<ExplanationItem> gaps, String status) {
      this(highlights, gaps, status, List.of(), List.of(), "");
    }

    public Explanation {
      highlights = List.copyOf(highlights);
      gaps = List.copyOf(gaps);
      verificationPoints = verificationPoints == null ? List.of() : List.copyOf(verificationPoints);
      qualityNotes = qualityNotes == null ? List.of() : List.copyOf(qualityNotes);
      summary = summary == null ? "" : summary;
    }
  }

  public record OverrideRequest(
      List<String> conditionIds, String reason, String expectedSnapshotHash) {}

  public record RevokeOverrideRequest(
      String overrideId, String reason, String expectedSnapshotHash) {}
}
