package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTalentContracts.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 有序锁定源候选人，身份合并不修改任何来源ACL、用途和截止。 */
@Service
public class HrCandidateMergeService {
  private final HrTalentMapper mapper;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;
  private final ObjectMapper json;

  public HrCandidateMergeService(
      HrTalentMapper mapper,
      HrTalentSearchService talent,
      HrAuditService audit,
      ObjectMapper json) {
    this.mapper = mapper;
    this.talent = talent;
    this.audit = audit;
    this.json = json;
  }

  @Transactional
  public MergeView merge(HrActor actor, MergeRequest request, String key) {
    HrAccessPolicy.require(actor, "hr:candidate:merge");
    reason(request.reason());
    if (request.sourceCandidateIds() == null
        || request.sourceCandidateIds().size() < 2
        || request.sourceCandidateIds().size() > 20
        || !request.sourceCandidateIds().contains(request.primaryCandidateId()))
      throw HrTalentSearchService.invalid();
    String hash = hash(request);
    String replay = operation(actor, "merge", key, hash);
    if (replay != null) return view(mapper.merge(actor.tenantId(), replay));
    var ids = new TreeSet<>(request.sourceCandidateIds());
    if (ids.size() != request.sourceCandidateIds().size()) throw HrTalentSearchService.invalid();
    for (String id : ids) {
      var c = mapper.lockCandidate(actor.tenantId(), id);
      if (!talent.visible(actor, c)) throw HrTalentSearchService.missing();
      HrAccessPolicy.requireFor(actor, "hr:candidate:merge", c.departmentId(), c.id(), "CANDIDATE");
      if (mapper.mergeForCandidate(actor.tenantId(), id) != null) throw conflict();
    }
    Instant now = Instant.now();
    var row =
        new HrTalentMapper.MergeRow(
            UUID.randomUUID().toString(),
            actor.tenantId(),
            request.primaryCandidateId(),
            write(ids),
            "ACTIVE",
            now,
            now.plus(Duration.ofDays(7)),
            1,
            actor.userId());
    mapper.insertMerge(row);
    for (String id : ids)
      mapper.insertSource(actor.tenantId(), id, request.primaryCandidateId(), row.id());
    mapper.insertOperation(actor.tenantId(), actor.userId(), "merge", key, hash, row.id());
    audit.append(
        actor,
        "CANDIDATE_MERGED",
        row.id(),
        mapper.candidate(actor.tenantId(), request.primaryCandidateId()).departmentId());
    return view(row);
  }

  @Transactional
  public MergeView revoke(HrActor actor, String id, Revocation request) {
    HrAccessPolicy.require(actor, "hr:candidate:merge");
    reason(request.reason());
    var row = mapper.merge(actor.tenantId(), id);
    if (row == null) throw HrTalentSearchService.missing();
    var sources =
        talent.authorizedSources(actor, row.primaryCandidateId(), "hr:candidate:merge", true);
    if (!row.revocableUntil().isAfter(Instant.now())
        || mapper.revokeMerge(actor.tenantId(), id, request.expectedVersion()) != 1)
      throw conflict();
    mapper.revokeSources(actor.tenantId(), id);
    for (var c : sources)
      mapper.staleMixed(actor.tenantId(), '%' + String.valueOf('"') + c.id() + '"' + '%');
    audit.append(actor, "MERGE_REVOKED", id, sources.getFirst().departmentId());
    return view(mapper.merge(actor.tenantId(), id));
  }

  public String operation(HrActor actor, String route, String key, String hash) {
    if (key == null || key.isBlank() || key.length() > 100) throw HrTalentSearchService.invalid();
    String result = mapper.operation(actor.tenantId(), actor.userId(), route, key, hash);
    if ("!CONFLICT".equals(result)) throw conflict();
    return result;
  }

  private MergeView view(HrTalentMapper.MergeRow row) {
    try {
      return new MergeView(
          row.id(),
          row.primaryCandidateId(),
          json.readValue(
              row.sourceIds(),
              json.getTypeFactory().constructCollectionType(List.class, String.class)),
          row.status(),
          row.createdAt(),
          row.revocableUntil(),
          row.version());
    } catch (Exception e) {
      throw new IllegalStateException("HR_MERGE_INTEGRITY_FAILED");
    }
  }

  private String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw HrTalentSearchService.invalid();
    }
  }

  private String hash(Object value) {
    return HrAuditService.hash(write(value));
  }

  public static void reason(String reason) {
    if (reason == null || reason.isBlank() || reason.length() > 300)
      throw HrTalentSearchService.invalid();
  }

  public static HrBusinessException conflict() {
    return new HrBusinessException("HR_VERSION_CONFLICT", "对象版本或状态已变化", 409);
  }
}
