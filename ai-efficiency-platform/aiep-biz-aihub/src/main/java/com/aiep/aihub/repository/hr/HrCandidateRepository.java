package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.HrCandidateRepositoryPort;
import org.springframework.stereotype.Repository;

@Repository
public class HrCandidateRepository implements HrCandidateRepositoryPort {
  public java.util.List<Snapshot> history(String tenantId, String candidateId) {
    return mapper.history(tenantId, candidateId);
  }

  private final HrCandidateMapper mapper;

  public HrCandidateRepository(HrCandidateMapper mapper) {
    this.mapper = mapper;
  }

  @org.springframework.transaction.annotation.Transactional
  public void create(Candidate candidate, Snapshot snapshot) {
    mapper.insertCandidate(candidate);
    mapper.insertSnapshot(snapshot);
  }

  public Candidate find(String tenantId, String id) {
    return mapper.find(tenantId, id);
  }

  public Snapshot snapshot(String tenantId, String id) {
    return mapper.snapshot(tenantId, id);
  }

  public void insertCandidate(Candidate value) {
    mapper.insertCandidate(value);
  }

  public void insertSnapshot(Snapshot value) {
    mapper.insertSnapshot(value);
  }

  public boolean advance(String tenantId, String id, String snapshotId, long expectedVersion) {
    return mapper.advance(tenantId, id, snapshotId, expectedVersion) == 1;
  }

  public void staleResults(String tenantId, String candidateId) {
    mapper.staleResults(tenantId, candidateId);
  }
}
