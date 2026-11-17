package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 先撤销可见性，再进行持久Saga；失败仅删除补偿，绝不恢复ACTIVE。 */
@Service
public class HrDeletionService {
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;
  private final ObjectProvider<HrDeletionEffectsPort> effects;
  private HrExpiredDeletionRegistrar expired;

  @org.springframework.beans.factory.annotation.Autowired
  public HrDeletionService(
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrAuditService audit,
      ObjectProvider<HrDeletionEffectsPort> effects,
      HrExpiredDeletionRegistrar expired) {
    this(mapper, talent, audit, effects);
    this.expired = expired;
  }

  public HrDeletionService(
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrAuditService audit,
      ObjectProvider<HrDeletionEffectsPort> effects) {
    this.mapper = mapper;
    this.talent = talent;
    this.audit = audit;
    this.effects = effects;
  }

  @Transactional
  public DeletionJob delete(HrActor actor, String id, DeleteRequest request) {
    HrAccessPolicy.require(actor, "hr:candidate:delete");
    HrCandidateMergeService.reason(request.reason());
    if (!request.confirmed()) throw HrTalentSearchService.invalid();
    var sources = talent.authorizedSources(actor, id, "hr:candidate:delete", true);
    var selected =
        sources.stream().filter(c -> c.id().equals(id)).findFirst().orElse(sources.getFirst());
    if (selected.version() != request.expectedVersion()) throw HrCandidateMergeService.conflict();
    HrTalentMapper.JobRow first = null;
    for (var c : sources) {
      mapper.lockCandidate(actor.tenantId(), c.id());
      if (mapper.tombstone(actor.tenantId(), c.id(), c.version()) != 1)
        throw HrCandidateMergeService.conflict();
      mapper.revokeCandidateGrants(actor.tenantId(), c.id());
      mapper.revokeAssignments(actor.tenantId(), c.id());
      mapper.revokeExports(actor.tenantId(), c.id());
      Instant now = Instant.now();
      var job =
          new HrTalentMapper.JobRow(
              UUID.randomUUID().toString(),
              actor.tenantId(),
              c.id(),
              c.departmentId(),
              "PENDING",
              "INDEX",
              0,
              now,
              now,
              null);
      mapper.insertJob(job);
      audit.append(actor, "CANDIDATE_DELETION_REQUESTED", c.id(), c.departmentId());
      if (first == null) first = job;
    }
    return view(first);
  }

  public DeletionJob get(HrActor actor, String id) {
    HrAccessPolicy.require(actor, "hr:candidate:delete");
    var row = mapper.job(actor.tenantId(), id);
    if (row == null) throw HrTalentSearchService.missing();
    HrAccessPolicy.department(actor, row.departmentId());
    return view(row);
  }

  @org.springframework.scheduling.annotation.Scheduled(fixedDelay = 60000)
  public void cleanupExpired() {
    if (expired == null) throw new IllegalStateException("HR_EXPIRY_TRANSACTION_REQUIRED");
    for (var c : mapper.expired(Instant.now())) {
      expired.register(c);
    }
    retryDue();
  }

  public void retryDue() {
    for (var row : mapper.dueJobs(Instant.now())) process(row);
  }

  public void process(HrTalentMapper.JobRow row) {
    var port = effects.getIfAvailable();
    try {
      if (port == null)
        throw new HrBusinessException("HR_DELETION_DEPENDENCY_NOT_READY", "删除依赖未就绪", 503);
      switch (row.step()) {
        case "INDEX" -> {
          port.deleteIndex(row.tenantId(), row.candidateId(), row.id() + ":index");
          mapper.advanceJob(row.tenantId(), row.id(), "INDEX", "BUSINESS");
        }
        case "BUSINESS" -> {
          mapper.deleteBusiness(row.tenantId(), row.candidateId());
          mapper.advanceJob(row.tenantId(), row.id(), "BUSINESS", "FILES");
        }
        case "FILES" -> {
          port.releaseFilesAndCaches(row.tenantId(), row.candidateId(), row.id() + ":files");
          mapper.completeCandidate(row.tenantId(), row.candidateId());
          mapper.completeJob(row.tenantId(), row.id());
        }
        default -> throw new IllegalStateException("HR_DELETION_STEP_INVALID");
      }
    } catch (Exception error) {
      int attempts = row.attempts() + 1;
      long[] delays = {60, 300, 1800, 7200, 21600};
      String code =
          error instanceof HrBusinessException
              ? "HR_DELETION_DEPENDENCY_NOT_READY"
              : "HR_DELETION_STEP_FAILED";
      mapper.failJob(
          row.tenantId(),
          row.id(),
          attempts,
          Instant.now().plusSeconds(delays[Math.min(attempts - 1, 4)]),
          code);
    }
  }

  private DeletionJob view(HrTalentMapper.JobRow row) {
    return new DeletionJob(
        row.id(),
        row.candidateId(),
        row.status(),
        row.step(),
        row.attempts(),
        row.nextAttemptAt(),
        row.createdAt(),
        "BLOCKED".equals(row.status())
            || !row.createdAt().plus(Duration.ofHours(24)).isAfter(Instant.now()),
        row.failureCode());
  }
}
