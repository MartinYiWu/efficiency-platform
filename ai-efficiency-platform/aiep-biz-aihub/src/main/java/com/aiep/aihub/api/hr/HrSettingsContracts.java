package com.aiep.aihub.api.hr;

import java.util.List;

/** 全局默认值只作用新对象；禁止属性和安全上界不可由客户端扩张。 */
public final class HrSettingsContracts {
  private HrSettingsContracts() {}

  public record Settings(
      String departmentId,
      String status,
      int retentionMonths,
      int confirmationWaitDays,
      int maxModelAttempts,
      int failedItemRetentionDays,
      int highThreshold,
      int middleThreshold,
      int lowThreshold,
      String noticeVersion,
      long maxFileBytes,
      long maxArchiveBytes,
      int maxBatchItems,
      long version,
      List<String> prohibitedAttributes,
      String authorizationText) {
    public Settings(
        String departmentId,
        String status,
        int retentionMonths,
        int confirmationWaitDays,
        int maxModelAttempts,
        int failedItemRetentionDays,
        int highThreshold,
        int middleThreshold,
        int lowThreshold,
        String noticeVersion,
        long maxFileBytes,
        long maxArchiveBytes,
        int maxBatchItems,
        long version,
        List<String> prohibitedAttributes) {
      this(
          departmentId,
          status,
          retentionMonths,
          confirmationWaitDays,
          maxModelAttempts,
          failedItemRetentionDays,
          highThreshold,
          middleThreshold,
          lowThreshold,
          noticeVersion,
          maxFileBytes,
          maxArchiveBytes,
          maxBatchItems,
          version,
          prohibitedAttributes,
          "");
    }

    public Settings {
      prohibitedAttributes =
          prohibitedAttributes == null ? List.of() : List.copyOf(prohibitedAttributes);
    }
  }

  public record SaveSettings(
      String departmentId,
      long expectedVersion,
      int retentionMonths,
      int confirmationWaitDays,
      int maxModelAttempts,
      int failedItemRetentionDays,
      int highThreshold,
      int middleThreshold,
      int lowThreshold,
      String noticeVersion,
      long maxFileBytes,
      long maxArchiveBytes,
      int maxBatchItems,
      String authorizationText) {}

  public record Publish(String departmentId, long expectedVersion) {}

  public record Version(long expectedVersion) {}

  public record Audit(
      String id,
      String departmentId,
      String kind,
      String objectId,
      String action,
      String actorId,
      long version,
      java.time.Instant at) {}
}
