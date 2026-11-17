package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrWorkbenchContracts.*;
import java.time.Instant;
import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface HrWorkbenchMapper {
  record Counts(
      long candidates,
      long scored,
      long filtered,
      long reviewRequired,
      long draftPositions,
      long pendingReview) {}

  default Counts counts(String tenant, Set<String> departments, Instant now) {
    return scopedCounts(tenant, departments, Set.of("*"), Set.of("*"), now);
  }

  default List<PositionProgress> positions(String tenant, Set<String> departments, Instant now) {
    return scopedPositions(tenant, departments, Set.of("*"), Set.of("*"), now);
  }

  Counts scopedCounts(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("candidateIds") Set<String> candidates,
      @Param("positionIds") Set<String> positions,
      @Param("now") Instant now);

  List<PositionProgress> scopedPositions(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("candidateIds") Set<String> candidates,
      @Param("positionIds") Set<String> positions,
      @Param("now") Instant now);

  long acquired(
      @Param("tenant") String tenant,
      @Param("departments") Set<String> departments,
      @Param("candidateIds") Set<String> candidates,
      @Param("start") Instant start,
      @Param("end") Instant end,
      @Param("now") Instant now);
}
