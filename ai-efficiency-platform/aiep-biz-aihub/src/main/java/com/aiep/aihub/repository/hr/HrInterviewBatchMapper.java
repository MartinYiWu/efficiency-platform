package com.aiep.aihub.repository.hr;

import org.apache.ibatis.annotations.*;

@Mapper
public interface HrInterviewBatchMapper {
  record Row(
      String id,
      String tenantId,
      String actorId,
      String kind,
      String status,
      String payload,
      String inputJson,
      String idempotencyKey,
      String inputHash) {}

  Row get(@Param("tenant") String tenant, @Param("id") String id, @Param("kind") String kind);

  Row replay(
      @Param("tenant") String tenant,
      @Param("actor") String actor,
      @Param("key") String key,
      @Param("kind") String kind);

  void insert(Row row);

  int start(@Param("tenant") String tenant, @Param("id") String id);

  int update(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("payload") String payload,
      @Param("status") String status);

  int recover();
}
