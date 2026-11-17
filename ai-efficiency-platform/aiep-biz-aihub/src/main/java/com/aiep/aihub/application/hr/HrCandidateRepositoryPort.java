package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;

public interface HrCandidateRepositoryPort {
  Candidate find(String tenantId, String id);

  Snapshot snapshot(String tenantId, String id);

  void create(Candidate candidate, Snapshot snapshot);

  void insertCandidate(Candidate candidate);

  void insertSnapshot(Snapshot snapshot);

  boolean advance(String tenantId, String id, String snapshotId, long expectedVersion);

  void staleResults(String tenantId, String candidateId);

  default java.util.List<Snapshot> history(String tenantId, String candidateId) {
    throw new IllegalStateException("HR_HISTORY_NOT_READY");
  }
}
