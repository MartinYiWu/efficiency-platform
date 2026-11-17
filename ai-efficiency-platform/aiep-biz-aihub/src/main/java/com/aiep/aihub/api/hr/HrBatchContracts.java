package com.aiep.aihub.api.hr;

import java.time.Instant;
import java.util.List;

/** 招聘采集和批次合同，授权用途与策略版本必须在开始处理前冻结。 */
public final class HrBatchContracts {
  private HrBatchContracts() {}

  public record Policy(
      String id,
      String authorizationText,
      int retentionMonths,
      int reviewWaitDays,
      int maximumAttempts,
      int failedRetentionDays,
      int highThreshold,
      int middleThreshold,
      int lowThreshold,
      long version) {}

  public record Format(String extension, boolean available, String reason) {}

  public record UploadPolicy(
      String policyVersionId, String authorizationText, List<Format> formats) {}

  public record CreateBatch(
      String positionId,
      String mode,
      String policyVersionId,
      boolean authorizationConfirmed,
      int maximumItems,
      String departmentId) {}

  public record BatchItem(
      String id,
      String filename,
      String status,
      String stage,
      String candidateId,
      String errorCode,
      String message,
      int progress,
      String contentHash) {
    public BatchItem(
        String id,
        String filename,
        String status,
        String stage,
        String candidateId,
        String errorCode,
        String message,
        int progress) {
      this(id, filename, status, stage, candidateId, errorCode, message, progress, null);
    }
  }

  public record Batch(
      String id,
      String positionId,
      String mode,
      String status,
      long version,
      List<BatchItem> items,
      Instant createdAt,
      int completedCount,
      int failedCount,
      int reviewCount,
      int totalCount) {}

  public record Version(long expectedVersion) {}

  public record TextUpload(String text, String filename) {}
}
