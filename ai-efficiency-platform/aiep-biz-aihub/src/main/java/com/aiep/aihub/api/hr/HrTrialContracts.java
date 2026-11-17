package com.aiep.aihub.api.hr;

import com.aiep.aihub.api.hr.HrPositionContracts.Draft;
import java.math.BigDecimal;
import java.util.*;

/** Sandbox结果隔离于正式匹配；盲标提交之前分数/标签/诊断不可见。 */
public final class HrTrialContracts {
  private HrTrialContracts() {}

  public record ExecutionOperation(
      String candidateId, String factSnapshotId, String runRef, int semanticBatches) {}

  public record ExecutionPlan(
      String trialId,
      String departmentId,
      long trialVersion,
      long version,
      List<ExecutionOperation> operations,
      int maximumNewHttpAttempts,
      long maximumCostMicrounits,
      String status,
      String errorCode,
      java.time.Instant deadline,
      String budgetRef,
      String planRef) {
    public ExecutionPlan {
      operations = List.copyOf(operations);
    }
  }

  public record PlanRequest(long expectedVersion) {}

  public record ExecuteRequest(long expectedVersion, long expectedPlanVersion) {}

  public record Create(
      String positionId,
      int sampleSize,
      List<String> candidateIds,
      long seed,
      long expectedPositionVersion) {}

  public record TrialResult(
      String candidateId,
      String status,
      String label,
      BigDecimal score,
      BigDecimal coverage,
      List<String> failedConditionIds,
      String factSnapshotId,
      String errorCode) {}

  public record Label(String candidateId, String label, String reason, String note) {}

  public record Labels(long expectedVersion, List<Label> labels) {}

  public record Trial(
      String id,
      String positionId,
      String departmentId,
      int sampleSize,
      int actualSize,
      long seed,
      String snapshotHash,
      long version,
      String status,
      List<TrialResult> results,
      List<Label> labels,
      String diagnosis,
      BigDecimal agreement,
      boolean verified,
      Draft frozenDraft,
      java.time.LocalDate asOfDate,
      Map<String, BigDecimal> hardConditionFailureRates,
      Long dictionaryVersion,
      Map<String, com.aiep.aihub.api.hr.HrPositionContracts.AssetBinding> bindings) {
    public Trial(
        String id,
        String positionId,
        String departmentId,
        int sampleSize,
        int actualSize,
        long seed,
        String snapshotHash,
        long version,
        String status,
        List<TrialResult> results,
        List<Label> labels,
        String diagnosis,
        BigDecimal agreement,
        boolean verified,
        Draft frozenDraft,
        java.time.LocalDate asOfDate,
        Map<String, BigDecimal> hardConditionFailureRates) {
      this(
          id,
          positionId,
          departmentId,
          sampleSize,
          actualSize,
          seed,
          snapshotHash,
          version,
          status,
          results,
          labels,
          diagnosis,
          agreement,
          verified,
          frozenDraft,
          asOfDate,
          hardConditionFailureRates,
          null,
          Map.of());
    }

    public Trial(
        String id,
        String positionId,
        String departmentId,
        int sampleSize,
        int actualSize,
        long seed,
        String snapshotHash,
        long version,
        String status,
        List<TrialResult> results,
        List<Label> labels,
        String diagnosis,
        BigDecimal agreement,
        boolean verified,
        Draft frozenDraft,
        java.time.LocalDate asOfDate) {
      this(
          id,
          positionId,
          departmentId,
          sampleSize,
          actualSize,
          seed,
          snapshotHash,
          version,
          status,
          results,
          labels,
          diagnosis,
          agreement,
          verified,
          frozenDraft,
          asOfDate,
          Map.of(),
          null,
          Map.of());
    }

    public Trial {
      bindings = bindings == null ? Map.of() : Map.copyOf(bindings);
      hardConditionFailureRates =
          hardConditionFailureRates == null ? Map.of() : Map.copyOf(hardConditionFailureRates);
      results = List.copyOf(results);
      labels = List.copyOf(labels);
    }
  }
}
