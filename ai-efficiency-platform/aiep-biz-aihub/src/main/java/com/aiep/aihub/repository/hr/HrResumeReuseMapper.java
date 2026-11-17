package com.aiep.aihub.repository.hr;

import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

/** 仅候选域内同租户归档hash索引查询，不联接平台私有文件表。 */
@Mapper
public interface HrResumeReuseMapper {
  record Row(
      String candidateId,
      String departmentId,
      String status,
      Instant expiresAt,
      String purposes,
      long snapshotVersion,
      String factsJson,
      String extractionJson) {}

  List<Row> find(
      @Param("tenant") String tenant,
      @Param("department") String department,
      @Param("hash") String hash,
      @Param("candidateIds") Set<String> candidateIds,
      @Param("now") Instant now);

  int recordHash(
      @Param("tenant") String tenant,
      @Param("candidate") String candidate,
      @Param("hash") String hash);
}
