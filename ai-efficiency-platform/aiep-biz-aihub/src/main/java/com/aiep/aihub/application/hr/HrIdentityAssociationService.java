package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** HMAC先按权限查源，再核验全部高质量联系方式；关联不合并来源授权。 */
@Service
public class HrIdentityAssociationService {
  private final HrTalentIdentityMapper identities;
  private final HrTalentMapper mapper;
  private final HrSourceAuthorization sources;
  private final HrSensitiveJsonCodec codec;
  private final HrTalentSearchService talent;
  private final HrAuditService audit;
  private final ObjectMapper json;

  public HrIdentityAssociationService(
      HrTalentIdentityMapper identities,
      HrTalentMapper mapper,
      HrSourceAuthorization sources,
      HrSensitiveJsonCodec codec,
      HrTalentSearchService talent,
      HrAuditService audit,
      ObjectMapper json) {
    this.identities = identities;
    this.mapper = mapper;
    this.sources = sources;
    this.codec = codec;
    this.talent = talent;
    this.audit = audit;
    this.json = json;
  }

  @Transactional
  public void associate(HrActor actor, Candidate incoming) {
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:read", incoming.departmentId(), incoming.id(), "CANDIDATE");
    var signals = sources.identitySignals(actor.tenantId(), incoming.id());
    Set<String> keys = new HashSet<>();
    for (var signal : signals) {
      if (signal.value() == null || signal.value().isBlank()) continue;
      String key = codec.searchKey(actor.tenantId(), signal.kind(), signal.value());
      keys.add(key);
      identities.signal(
          new HrTalentIdentityMapper.Signal(
              actor.tenantId(),
              incoming.id(),
              signal.kind(),
              key,
              signal.quality(),
              signal.shared(),
              signal.conflict()));
    }
    if (keys.isEmpty()) return;
    Set<String> candidates = new TreeSet<>();
    for (String department : HrAccessPolicy.departmentsFor(actor, "hr:candidate:read")) {
      var allowed =
          HrAccessPolicy.objectIdsFor(actor, "hr:candidate:read", department, "CANDIDATE");
      if (!allowed.isEmpty())
        candidates.addAll(
            identities.possible(
                actor.tenantId(), incoming.id(), keys, Set.of(department), allowed, Instant.now()));
    }
    var snapshot = mapper.snapshot(actor.tenantId(), incoming.currentSnapshotId());
    if (snapshot == null) throw HrTalentSearchService.missing();
    for (String id : candidates) {
      var existing = talent.authorized(actor, id, "hr:candidate:read");
      var decision = HrTalentDedup.identity(signals, sources.identitySignals(actor.tenantId(), id));
      String status =
          decision == HrTalentDedup.IdentityDecision.AUTO_LINK
              ? "AUTO_LINKED"
              : decision == HrTalentDedup.IdentityDecision.MANUAL_REVIEW ? "SUGGESTED" : null;
      if (status == null) continue;
      String primary = id;
      if ("AUTO_LINKED".equals(status)) primary = linkSources(actor, existing, incoming);
      identities.associate(
          new HrTalentIdentityMapper.Association(
              UUID.randomUUID().toString(),
              actor.tenantId(),
              primary,
              incoming.id(),
              snapshot.resumeVersionId(),
              status,
              Instant.now()));
      audit.append(
          actor,
          "AUTO_LINKED".equals(status) ? "IDENTITY_AUTO_ASSOCIATED" : "IDENTITY_REVIEW_SUGGESTED",
          incoming.id(),
          incoming.departmentId());
      if ("AUTO_LINKED".equals(status)) break;
    }
  }

  private String linkSources(HrActor actor, Candidate existing, Candidate incoming) {
    var merge = mapper.mergeForCandidate(actor.tenantId(), existing.id());
    var ids = new TreeSet<String>();
    if (merge != null) {
      for (var c : talent.authorizedSources(actor, existing.id(), "hr:candidate:read", true))
        ids.add(c.id());
    } else ids.add(existing.id());
    ids.add(incoming.id());
    for (String id : ids) {
      var c = mapper.lockCandidate(actor.tenantId(), id);
      if (!talent.visible(actor, c)) throw HrTalentSearchService.missing();
      HrAccessPolicy.requireFor(actor, "hr:candidate:read", c.departmentId(), c.id(), "CANDIDATE");
    }
    String primary = merge == null ? existing.id() : merge.primaryCandidateId();
    Instant now = Instant.now();
    String id = UUID.randomUUID().toString();
    String encoded;
    try {
      encoded = json.writeValueAsString(ids);
    } catch (Exception error) {
      throw HrTalentSearchService.invalid();
    }
    if (merge == null) {
      mapper.insertMerge(
          new HrTalentMapper.MergeRow(
              id,
              actor.tenantId(),
              primary,
              encoded,
              "ACTIVE",
              now,
              now.plus(Duration.ofDays(7)),
              1,
              actor.userId()));
    } else {
      if (mapper.appendMergeSources(actor.tenantId(), merge.id(), merge.version(), encoded) != 1)
        throw HrCandidateMergeService.conflict();
      id = merge.id();
    }
    for (String source : ids) mapper.insertSource(actor.tenantId(), source, primary, id);
    return primary;
  }
}
