package com.aiep.aihub.repository.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class HrMatchingRepository {
  public java.util.List<HrMatchingMapper.CountRow> statistics(
      com.aiep.aihub.api.hr.HrActor actor, String position, String version) {
    return actor.departmentIds().isEmpty()
            || actor.positionIds().isEmpty()
            || actor.candidateIds().isEmpty()
        ? java.util.List.of()
        : mapper.statistics(
            actor.tenantId(),
            actor.departmentIds(),
            position,
            null,
            version,
            null,
            actor.positionIds(),
            actor.candidateIds(),
            actor.authenticated() ? actor.grants() : java.util.List.of(),
            java.time.Instant.now());
  }

  private final HrMatchingMapper mapper;
  private final HrCandidateMapper candidates;
  private HrExecutionMapper events;

  @org.springframework.beans.factory.annotation.Autowired
  public HrMatchingRepository(
      HrMatchingMapper mapper, HrCandidateMapper candidates, HrExecutionMapper events) {
    this(mapper, candidates);
    this.events = events;
  }

  public HrMatchingRepository(HrMatchingMapper mapper, HrCandidateMapper candidates) {
    this.mapper = mapper;
    this.candidates = candidates;
  }

  public Run findIdempotency(String tenantId, String key) {
    return mapper.findIdempotency(tenantId, key);
  }

  public List<Run> recentRuns(
      String tenant, String candidate, String position, java.time.Instant since, int limit) {
    if (limit < 1 || limit > 100) throw new IllegalArgumentException("HR_RUN_QUERY_LIMIT_INVALID");
    return mapper.recentRuns(tenant, candidate, position, since, limit);
  }

  public void insertRun(Run run) {
    mapper.insertRun(run);
    event(run.tenantId(), run.id(), 1, run.status(), run.resultId(), run.failureCode());
  }

  public boolean start(String tenantId, String id) {
    boolean changed = mapper.startRun(tenantId, id) == 1;
    if (changed) event(tenantId, id, 2, "RUNNING", null, null);
    return changed;
  }

  public boolean cancel(String tenantId, String id) {
    boolean changed = mapper.cancelRun(tenantId, id) == 1;
    if (changed) event(tenantId, id, 3, "CANCEL_PENDING", null, null);
    return changed;
  }

  @Transactional
  public void cancelScope(String tenant, String scope) {
    var runs = mapper.lockScopeRuns(tenant, scope, false);
    if (runs.isEmpty()) return;
    mapper.cancelScope(tenant, scope);
    for (var run : runs) event(tenant, run.id(), 3, "CANCEL_PENDING", null, null);
  }

  @Transactional
  public void confirmScopeCancellation(String tenant, String scope) {
    var runs = mapper.lockScopeRuns(tenant, scope, true);
    if (runs.isEmpty()) return;
    mapper.confirmScopeCancellation(tenant, scope);
    for (var run : runs) event(tenant, run.id(), 4, "CANCELLED", null, null);
  }

  public void confirmCancellation(String tenantId, String id, boolean confirmed) {
    mapper.confirmCancellation(tenantId, id, confirmed);
    if (confirmed) event(tenantId, id, 4, "CANCELLED", null, null);
  }

  @Transactional
  public boolean completeRun(
      String tenantId, String runId, SemanticSnapshot semantic, ResultSnapshot result) {
    Run run = mapper.lockRun(tenantId, runId);
    if (run == null || !run.status().equals("RUNNING")) return false;
    com.aiep.aihub.api.hr.HrCandidateContracts.Candidate candidate =
        candidates.lockCandidate(tenantId, result.candidateId());
    if (candidate == null || !candidate.currentSnapshotId().equals(result.factSnapshotId())) {
      mapper.finishRun(tenantId, runId, "FAILED", null, "HR_FACT_SNAPSHOT_CHANGED");
      event(tenantId, runId, 4, "FAILED", null, "HR_FACT_SNAPSHOT_CHANGED");
      return false;
    }
    complete(semantic, result);
    boolean changed = mapper.finishRun(tenantId, runId, "SUCCEEDED", result.id(), null) == 1;
    if (changed) event(tenantId, runId, 4, "SUCCEEDED", result.id(), null);
    return changed;
  }

  @Transactional
  public boolean completeBatch(
      String tenantId,
      String runId,
      List<SemanticSnapshot> semantics,
      List<ResultSnapshot> results) {
    Run run = mapper.lockRun(tenantId, runId);
    if (run == null || !run.status().equals("RUNNING")) return false;
    for (ResultSnapshot result :
        results.stream()
            .sorted(java.util.Comparator.comparing(ResultSnapshot::candidateId))
            .toList()) {
      var candidate = candidates.lockCandidate(tenantId, result.candidateId());
      if (candidate == null || !candidate.currentSnapshotId().equals(result.factSnapshotId())) {
        mapper.finishRun(tenantId, runId, "FAILED", null, "HR_FACT_SNAPSHOT_CHANGED");
        event(tenantId, runId, 4, "FAILED", null, "HR_FACT_SNAPSHOT_CHANGED");
        return false;
      }
    }
    for (int i = 0; i < results.size(); i++) complete(semantics.get(i), results.get(i));
    boolean changed =
        mapper.finishRun(tenantId, runId, "SUCCEEDED", results.getFirst().id(), null) == 1;
    if (changed) event(tenantId, runId, 4, "SUCCEEDED", results.getFirst().id(), null);
    return changed;
  }

  public Run run(String tenantId, String id) {
    return mapper.run(tenantId, id);
  }

  public void finishRun(String tenantId, String id, String status, String resultId, String code) {
    if (mapper.finishRun(tenantId, id, status, resultId, code) != 1)
      throw new IllegalStateException("HR_RUN_STATE_CONFLICT");
    event(tenantId, id, 4, status, resultId, code);
  }

  public SemanticSnapshot semantic(String tenantId, String id) {
    return mapper.semantic(tenantId, id);
  }

  public ResultSnapshot result(String tenantId, String id) {
    return mapper.result(tenantId, id);
  }

  @Transactional
  public boolean replaceCurrent(String tenantId, String sourceId, ResultSnapshot result) {
    var candidate = candidates.lockCandidate(tenantId, result.candidateId());
    if (candidate == null || !candidate.currentSnapshotId().equals(result.factSnapshotId()))
      return false;
    ResultSnapshot source = mapper.lockResult(tenantId, sourceId);
    if (source == null
        || !source.status().equals("CURRENT")
        || !source.candidateId().equals(result.candidateId())
        || !source.positionId().equals(result.positionId())) return false;
    complete(null, result);
    return true;
  }

  public List<ResultSnapshot> list(
      String tenantId,
      Set<String> departments,
      String positionId,
      String candidateId,
      String configVersion,
      String businessStatus,
      Set<String> positionIds,
      Set<String> candidateIds,
      int offset,
      int limit) {
    return listGranted(
        tenantId,
        departments,
        positionId,
        candidateId,
        configVersion,
        businessStatus,
        positionIds,
        candidateIds,
        offset,
        limit,
        List.of());
  }

  public List<ResultSnapshot> listGranted(
      String tenantId,
      Set<String> departments,
      String positionId,
      String candidateId,
      String configVersion,
      String businessStatus,
      Set<String> positionIds,
      Set<String> candidateIds,
      int offset,
      int limit,
      List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants) {
    return departments.isEmpty() || positionIds.isEmpty() || candidateIds.isEmpty()
        ? List.of()
        : mapper.list(
            tenantId,
            departments,
            positionId,
            candidateId,
            configVersion,
            businessStatus,
            positionIds,
            candidateIds,
            offset,
            limit,
            grants,
            java.time.Instant.now());
  }

  public long count(
      String tenantId,
      Set<String> departments,
      String positionId,
      String candidateId,
      String configVersion,
      String businessStatus) {
    return count(
        tenantId,
        departments,
        positionId,
        candidateId,
        configVersion,
        businessStatus,
        Set.of("*"),
        Set.of("*"));
  }

  public long count(
      String tenantId,
      Set<String> departments,
      String positionId,
      String candidateId,
      String configVersion,
      String businessStatus,
      Set<String> positionIds,
      Set<String> candidateIds) {
    return countGranted(
        tenantId,
        departments,
        positionId,
        candidateId,
        configVersion,
        businessStatus,
        positionIds,
        candidateIds,
        List.of());
  }

  public long countGranted(
      String tenantId,
      Set<String> departments,
      String positionId,
      String candidateId,
      String configVersion,
      String businessStatus,
      Set<String> positionIds,
      Set<String> candidateIds,
      List<com.aiep.aihub.api.hr.HrActor.GrantScope> grants) {
    return departments.isEmpty() || positionIds.isEmpty() || candidateIds.isEmpty()
        ? 0
        : mapper.count(
            tenantId,
            departments,
            positionId,
            candidateId,
            configVersion,
            businessStatus,
            positionIds,
            candidateIds,
            grants,
            java.time.Instant.now());
  }

  @Transactional
  public void complete(SemanticSnapshot semantic, ResultSnapshot result) {
    if (semantic != null) mapper.insertSemantic(semantic);
    if (result.status().equals("CURRENT"))
      mapper.supersede(result.tenantId(), result.candidateId(), result.positionId(), result.id());
    mapper.insertResult(result);
  }

  private void event(
      String tenant, String run, long sequence, String status, String result, String failure) {
    if (events != null)
      events.recordEvent(
          new HrExecutionMapper.EventRow(
              tenant, run, sequence, status, result, failure, java.time.Instant.now()));
  }
}
