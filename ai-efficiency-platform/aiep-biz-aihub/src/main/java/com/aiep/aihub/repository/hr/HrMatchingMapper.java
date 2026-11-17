package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.*;

@Mapper
public interface HrMatchingMapper {
  List<Run> recentRuns(
      @Param("tenantId") String tenant,
      @Param("candidateId") String candidate,
      @Param("positionId") String position,
      @Param("since") java.time.Instant since,
      @Param("limit") int limit);

  List<Run> lockScopeRuns(
      @Param("tenantId") String tenant,
      @Param("scope") String scope,
      @Param("pendingOnly") boolean pendingOnly);

  int cancelScope(@Param("tenantId") String tenant, @Param("scope") String scope);

  int confirmScopeCancellation(@Param("tenantId") String tenant, @Param("scope") String scope);

  record CountRow(String businessStatus, String band, long count) {}

  List<CountRow> statistics(
      @Param("tenantId") String tenant,
      @Param("departmentIds") Set<String> departments,
      @Param("positionId") String position,
      @Param("candidateId") String candidate,
      @Param("configVersion") String version,
      @Param("businessStatus") String status,
      @Param("positionIds") Set<String> positions,
      @Param("candidateIds") Set<String> candidates,
      @Param("grants") List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants,
      @Param("now") java.time.Instant now);

  Run findIdempotency(
      @Param("tenantId") String tenantId, @Param("idempotencyKey") String idempotencyKey);

  int insertRun(Run run);

  int startRun(@Param("tenantId") String tenantId, @Param("id") String id);

  int cancelRun(@Param("tenantId") String tenantId, @Param("id") String id);

  int confirmCancellation(
      @Param("tenantId") String tenantId,
      @Param("id") String id,
      @Param("confirmed") boolean confirmed);

  Run lockRun(@Param("tenantId") String tenantId, @Param("id") String id);

  int finishRun(
      @Param("tenantId") String tenantId,
      @Param("id") String id,
      @Param("status") String status,
      @Param("resultId") String resultId,
      @Param("failureCode") String failureCode);

  Run run(@Param("tenantId") String tenantId, @Param("id") String id);

  int insertSemantic(SemanticSnapshot snapshot);

  SemanticSnapshot semantic(@Param("tenantId") String tenantId, @Param("id") String id);

  int insertResult(ResultSnapshot snapshot);

  ResultSnapshot result(@Param("tenantId") String tenantId, @Param("id") String id);

  ResultSnapshot lockResult(@Param("tenantId") String tenantId, @Param("id") String id);

  List<ResultSnapshot> list(
      @Param("tenantId") String tenantId,
      @Param("departmentIds") Set<String> departmentIds,
      @Param("positionId") String positionId,
      @Param("candidateId") String candidateId,
      @Param("configVersion") String configVersion,
      @Param("businessStatus") String businessStatus,
      @Param("positionIds") Set<String> positionIds,
      @Param("candidateIds") Set<String> candidateIds,
      @Param("offset") int offset,
      @Param("limit") int limit,
      @Param("grants") List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants,
      @Param("now") java.time.Instant now);

  long count(
      @Param("tenantId") String tenantId,
      @Param("departmentIds") Set<String> departmentIds,
      @Param("positionId") String positionId,
      @Param("candidateId") String candidateId,
      @Param("configVersion") String configVersion,
      @Param("businessStatus") String businessStatus,
      @Param("positionIds") Set<String> positionIds,
      @Param("candidateIds") Set<String> candidateIds,
      @Param("grants") List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants,
      @Param("now") java.time.Instant now);

  int supersede(
      @Param("tenantId") String tenantId,
      @Param("candidateId") String candidateId,
      @Param("positionId") String positionId,
      @Param("newId") String newId);
}
