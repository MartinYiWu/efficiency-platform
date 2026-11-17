package com.aiep.aihub.repository.hr;

import org.apache.ibatis.annotations.*;

@Mapper
public interface HrSpecialMarksMapper {
  void deleteForSource(@Param("tenant") String tenant, @Param("candidate") String candidate);

  record Pair(String tenant, String left, String right, long leftVersion, long rightVersion) {}

  boolean distinct(Pair pair);

  void confirm(
      @Param("pair") Pair pair,
      @Param("actor") String actor,
      @Param("reason") String reason,
      @Param("now") java.time.Instant now);
}
