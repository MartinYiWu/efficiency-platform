package com.aiep.aihub.repository.hr;

import java.time.Instant;
import org.apache.ibatis.annotations.*;

@Mapper
public interface HrTalentSemanticMapper {
  void source(
      @Param("tenant") String tenant,
      @Param("job") String job,
      @Param("candidate") String candidate);

  void deleteJobsForSource(@Param("tenant") String tenant, @Param("candidate") String candidate);

  void deleteSourceRefs(@Param("tenant") String tenant, @Param("candidate") String candidate);

  record Row(
      String id,
      String tenantId,
      String actorId,
      String status,
      String inputJson,
      String resultJson,
      String idempotencyKey,
      String requestHash,
      Instant createdAt,
      Instant updatedAt) {}

  void insert(Row row);

  Row find(@Param("tenant") String tenant, @Param("id") String id);

  Row replay(
      @Param("tenant") String tenant, @Param("actor") String actor, @Param("key") String key);

  int update(
      @Param("tenant") String tenant,
      @Param("id") String id,
      @Param("expected") String expected,
      @Param("status") String status,
      @Param("input") String input,
      @Param("result") String result,
      @Param("now") Instant now);

  void recover();
}
