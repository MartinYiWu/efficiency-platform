package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.*;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 指派到期和撤销即时生效；面试官读取仅返回安全题集投影。 */
@Service
public class HrInterviewAssignmentService {
  private final HrTalentMapper mapper;
  private final HrInterviewService interviews;
  private final HrPositionService positions;
  private final InterviewViewAssembler assembler;
  private final HrAuditService audit;

  public HrInterviewAssignmentService(
      HrTalentMapper mapper,
      HrInterviewService interviews,
      HrPositionService positions,
      InterviewViewAssembler assembler,
      HrAuditService audit) {
    this.mapper = mapper;
    this.interviews = interviews;
    this.positions = positions;
    this.assembler = assembler;
    this.audit = audit;
  }

  @Transactional
  public Assignment assign(HrActor actor, AssignRequest request) {
    HrAccessPolicy.require(actor, "hr:interview:assign");
    var set = interviews.get(actor, request.setId(), request.setVersion());
    if (!"READY".equals(set.status())) throw HrCandidateMergeService.conflict();
    var candidate = mapper.candidate(actor.tenantId(), set.candidateId());
    HrAccessPolicy.requireFor(
        actor, "hr:interview:assign", candidate.departmentId(), candidate.id(), "CANDIDATE");
    Instant now = Instant.now();
    Instant expiry =
        request.expiresAt() == null ? now.plus(Duration.ofDays(7)) : request.expiresAt();
    if (request.interviewerId() == null
        || request.interviewerId().isBlank()
        || expiry.isBefore(now.plus(Duration.ofHours(1)))
        || expiry.isAfter(now.plus(Duration.ofDays(30)))) throw HrTalentSearchService.invalid();
    var row =
        new HrTalentMapper.AssignmentRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            set.id(),
            set.version(),
            request.interviewerId(),
            expiry,
            "ACTIVE",
            actor.userId());
    mapper.insertAssignment(row);
    audit.append(
        actor,
        "INTERVIEW_ASSIGNED",
        row.id(),
        positions.get(actor, set.positionId()).departmentId());
    return view(row);
  }

  public InterviewGuide assigned(HrActor actor, String id) {
    var a = mapper.assignment(actor.tenantId(), id);
    if (a == null
        || !a.interviewerId().equals(actor.userId())
        || !"ACTIVE".equals(a.status())
        || !a.expiresAt().isAfter(Instant.now())) throw HrTalentSearchService.missing();
    var row = mapper.set(actor.tenantId(), a.setId(), a.setVersion());
    if (row == null || !"READY".equals(row.status()))
      throw HrTalentSearchService.missing(); /* 指派不扩大源授权；源过期或删除后所有角色均立即不可读。 */
    var candidate = mapper.candidate(actor.tenantId(), row.candidateId());
    if (candidate == null
        || !"ACTIVE".equals(candidate.status())
        || candidate.expiresAt() == null
        || !candidate.expiresAt().isAfter(Instant.now())) throw HrTalentSearchService.missing();
    interviews.requireLiveProvenance(row);
    return assembler.assemble(interviews.decode(row), "岗位面试指南");
  }

  public InterviewGuide preview(HrActor actor, String id) {
    var set = interviews.get(actor, id, null);
    if (!"READY".equals(set.status())) throw HrCandidateMergeService.conflict();
    return assembler.assemble(set, positions.get(actor, set.positionId()).name());
  }

  @Transactional
  public void revoke(HrActor actor, String id, String reason) {
    HrAccessPolicy.require(actor, "hr:interview:assign");
    HrCandidateMergeService.reason(reason);
    var row = mapper.assignment(actor.tenantId(), id);
    if (row == null) throw HrTalentSearchService.missing();
    var set = interviews.get(actor, row.setId(), row.setVersion());
    var candidate = mapper.candidate(actor.tenantId(), set.candidateId());
    HrAccessPolicy.requireFor(
        actor, "hr:interview:assign", candidate.departmentId(), candidate.id(), "CANDIDATE");
    if (mapper.revokeAssignment(actor.tenantId(), id) != 1)
      throw HrCandidateMergeService.conflict();
    audit.append(
        actor,
        "INTERVIEW_ASSIGNMENT_REVOKED",
        id,
        positions.get(actor, set.positionId()).departmentId());
  }

  private Assignment view(HrTalentMapper.AssignmentRow r) {
    return new Assignment(
        r.id(), r.setId(), r.setVersion(), r.interviewerId(), r.expiresAt(), r.status());
  }
}
