package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrTalentContracts.ContactView;
import com.aiep.aihub.repository.hr.HrExecutionMapper;
import com.fasterxml.jackson.databind.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;

/** 来源授权、身份信号及原块映射独立加密保存，不进入模型输入或公共列表。 */
@Service
public class HrSourceAuthorization implements HrContactIdentityPort {
  public void confirmationState(String tenant, String candidate, String state) {
    if (!Set.of("WAITING", "SKIPPED", "CONFIRMED").contains(state))
      throw new IllegalArgumentException("HR_CONFIRMATION_STATE_INVALID");
    mapper.confirmationState(tenant, candidate, state);
  }

  public String executionScope(String tenant, String candidate) {
    if (batches == null) return null;
    var item = batches.candidateItem(tenant, candidate);
    return item == null ? null : "hr-import-" + item.id();
  }

  private com.aiep.aihub.repository.hr.HrBatchMapper batches;

  @org.springframework.beans.factory.annotation.Autowired
  public HrSourceAuthorization(
      HrExecutionMapper mapper,
      HrSensitiveJsonCodec codec,
      ObjectMapper json,
      com.aiep.aihub.repository.hr.HrBatchMapper batches) {
    this(mapper, codec, json);
    this.batches = batches;
  }

  private final HrExecutionMapper mapper;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;

  public HrSourceAuthorization(
      HrExecutionMapper mapper, HrSensitiveJsonCodec codec, ObjectMapper json) {
    this.mapper = mapper;
    this.codec = codec;
    this.json = json;
  }

  public void register(
      HrActor actor,
      Candidate candidate,
      JsonNode extracted,
      Set<String> purposes,
      int waitDays,
      String fileId) {
    try {
      mapper.source(
          new HrExecutionMapper.SourceRow(
              actor.tenantId(),
              candidate.id(),
              candidate.consentPolicyId(),
              String.join(",", new TreeSet<>(purposes)),
              codec.seal(json.writeValueAsString(extracted.path("identity"))),
              codec.seal(json.writeValueAsString(extracted)),
              fileId,
              candidate.acquiredAt().plus(Duration.ofDays(waitDays)),
              "WAITING"));
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_SOURCE_ENCODING_FAILED");
    }
  }

  public void requireUse(HrActor actor, Candidate candidate, String purpose) {
    HrAccessPolicy.department(actor, candidate.departmentId());
    HrAccessPolicy.candidate(actor, candidate.id());
    if (!"ACTIVE".equals(candidate.status())
        || candidate.expiresAt() == null
        || !candidate.expiresAt().isAfter(Instant.now())) throw HrPositionService.missing();
    var source = mapper.sourceByCandidate(actor.tenantId(), candidate.id());
    if (source == null || !Set.of(source.purposes().split(",")).contains(purpose))
      throw new HrBusinessException("HR_PERMISSION_PURPOSE_DENIED", "来源授权不包含此用途", 403);
  }

  public void requireMatching(HrActor actor, Candidate candidate, String targetPosition) {
    HrAccessPolicy.requireFor(
        actor, "hr:candidate:read", candidate.departmentId(), candidate.id(), "CANDIDATE");
    if (!"ACTIVE".equals(candidate.status())
        || candidate.expiresAt() == null
        || !candidate.expiresAt().isAfter(Instant.now())) throw HrPositionService.missing();
    var source = mapper.sourceByCandidate(actor.tenantId(), candidate.id());
    if (source == null)
      throw new HrBusinessException("HR_PERMISSION_PURPOSE_DENIED", "来源授权用途缺失", 403);
    Set<String> purposes = new HashSet<>(Arrays.asList(source.purposes().split(",")));
    if (purposes.contains("TALENT_POOL")) return;
    if (purposes.contains("RECRUITMENT") && batches != null) {
      var batch = batches.candidateBatch(actor.tenantId(), candidate.id());
      if (batch != null && targetPosition.equals(batch.positionId())) return;
    }
    throw new HrBusinessException("HR_PERMISSION_PURPOSE_DENIED", "来源仅授权原招聘岗位，不能用于本岗位试跑或匹配", 403);
  }

  @Override
  public ContactView read(String tenantId, String candidateId) {
    var source = mapper.sourceByCandidate(tenantId, candidateId);
    if (source == null) throw HrPositionService.missing();
    try {
      var identity = json.readTree(codec.open(source.identityJson()));
      return new ContactView(
          candidateId, one(identity.path("phones")), one(identity.path("emails")));
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new HrBusinessException("HR_IDENTITY_INTEGRITY_FAILED", "联系信息无法核验", 503);
    }
  }

  private static String one(JsonNode values) {
    Set<String> known = new HashSet<>();
    for (JsonNode n : values)
      if (!n.path("conflict").asBoolean()
          && n.path("quality").asInt() == 100
          && n.path("value").isTextual()) known.add(n.path("value").asText());
    return known.size() == 1 ? known.iterator().next() : null;
  }

  public void requireLiveUse(String tenant, String candidate, String purpose) {
    var source = mapper.sourceByCandidate(tenant, candidate);
    if (source == null || !Set.of(source.purposes().split(",")).contains(purpose))
      throw new HrBusinessException("HR_PERMISSION_PURPOSE_DENIED", "来源用途已失效", 403);
  }

  public List<HrTalentDedup.ContactSignal> identitySignals(String tenant, String candidate) {
    var source = mapper.sourceByCandidate(tenant, candidate);
    if (source == null) return List.of();
    try {
      var identity = json.readTree(codec.open(source.identityJson()));
      List<HrTalentDedup.ContactSignal> signals = new ArrayList<>();
      for (String kind : List.of("PHONE", "EMAIL"))
        for (JsonNode n : identity.path(kind.equals("PHONE") ? "phones" : "emails"))
          if (n.path("value").isTextual())
            signals.add(
                new HrTalentDedup.ContactSignal(
                    kind,
                    n.path("value").asText(),
                    n.path("quality").asInt(),
                    n.path("shared").asBoolean(),
                    n.path("conflict").asBoolean()));
      return List.copyOf(signals);
    } catch (com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IllegalStateException("HR_IDENTITY_INTEGRITY_FAILED");
    }
  }
}
