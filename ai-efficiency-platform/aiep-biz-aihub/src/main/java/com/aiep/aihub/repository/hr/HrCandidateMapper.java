package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface HrCandidateMapper {
  java.util.List<Snapshot> history(
      @Param("tenantId") String tenant, @Param("candidateId") String candidate);

  default Candidate lockCandidate(String tenantId, String id) {
    return lockActive(tenantId, id, java.time.Instant.now());
  }

  Candidate lockActive(
      @Param("tenantId") String tenantId,
      @Param("id") String id,
      @Param("now") java.time.Instant now);

  default Candidate find(String tenantId, String id) {
    return findActive(tenantId, id, java.time.Instant.now());
  }

  Candidate findActive(
      @Param("tenantId") String tenantId,
      @Param("id") String id,
      @Param("now") java.time.Instant now);

  Snapshot snapshot(@Param("tenantId") String tenantId, @Param("id") String id);

  int insertCandidate(Candidate candidate);

  int insertSnapshot(Snapshot snapshot);

  int advance(
      @Param("tenantId") String tenantId,
      @Param("id") String id,
      @Param("snapshotId") String snapshotId,
      @Param("expectedVersion") long expectedVersion);

  int staleResults(@Param("tenantId") String tenantId, @Param("candidateId") String candidateId);
}
