package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface HrBatchMapper {
  record PolicyRow(String id, String tenantId, String payload, long version, Instant createdAt) {}

  record BatchRow(
      String id,
      String tenantId,
      String departmentId,
      String userId,
      String positionId,
      String mode,
      String policyId,
      int maximumItems,
      String status,
      long version,
      Instant createdAt,
      String idempotencyKey,
      String requestHash) {}

  record ItemRow(
      String id,
      String tenantId,
      String batchId,
      String filename,
      String encryptedContent,
      String contentHash,
      String status,
      String stage,
      String candidateId,
      String errorCode,
      int progress) {}

  PolicyRow latestPolicy(@Param("tenant") String tenant);

  PolicyRow policy(@Param("tenant") String tenant, @Param("id") String id);

  void insertPolicy(PolicyRow row);

  BatchRow batch(@Param("tenant") String tenant, @Param("id") String id);

  BatchRow lockBatch(@Param("tenant") String tenant, @Param("id") String id);

  BatchRow idempotency(@Param("tenant") String tenant, @Param("key") String key);

  void insertBatch(BatchRow row);

  List<ItemRow> items(@Param("tenant") String tenant, @Param("id") String id);

  ItemRow item(@Param("tenant") String tenant, @Param("id") String id);

  BatchRow candidateBatch(@Param("tenant") String tenant, @Param("candidate") String candidate);

  ItemRow candidateItem(@Param("tenant") String tenant, @Param("candidate") String candidate);

  int addItem(ItemRow row);

  int advance(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("expected") long expected,
      @Param("from") String from,
      @Param("to") String to);

  int itemState(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("from") String from,
      @Param("to") String to,
      @Param("stage") String stage,
      @Param("candidate") String candidate,
      @Param("error") String error,
      @Param("progress") int progress);

  int finish(@Param("tenant") String tenant, @Param("id") String id);

  int cancel(@Param("tenant") String tenant, @Param("id") String id);

  int pendingCancel(@Param("tenant") String tenant, @Param("id") String id);

  int block(@Param("tenant") String tenant, @Param("id") String id);
}
