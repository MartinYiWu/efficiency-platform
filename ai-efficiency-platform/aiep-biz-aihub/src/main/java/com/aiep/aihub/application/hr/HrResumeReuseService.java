package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.Facts;
import com.aiep.aihub.repository.hr.HrResumeReuseMapper;
import com.fasterxml.jackson.databind.*;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;

/** 相同原件仅复用已授权原始解析，人工修正不传播到新采集，访问失败静默回退新解析。 */
@Service
public class HrResumeReuseService {
  public record Reuse(Facts originalFacts, JsonNode extraction) {}

  private final HrResumeReuseMapper mapper;
  private final HrSensitiveJsonCodec codec;
  private final ObjectMapper json;

  public HrResumeReuseService(
      HrResumeReuseMapper mapper, HrSensitiveJsonCodec codec, ObjectMapper json) {
    this.mapper = mapper;
    this.codec = codec;
    this.json = json;
  }

  public Reuse find(HrActor actor, String department, String sha256, String filename) {
    if (sha256 == null || !sha256.matches("[0-9a-f]{64}"))
      throw HrPositionService.invalid("原件SHA-256无效");
    if (!actor.permissions().contains("hr:candidate:read")) return null;
    Set<String> allowed;
    try {
      HrAccessPolicy.requireFor(actor, "hr:candidate:read", department, null, "CANDIDATE");
      allowed = HrAccessPolicy.objectIdsFor(actor, "hr:candidate:read", department, "CANDIDATE");
    } catch (HrBusinessException denied) {
      if (denied.status() == 403 || denied.status() == 404) return null;
      throw denied;
    }
    if (allowed.isEmpty()) return null;
    Instant now = Instant.now();
    for (var row : mapper.find(actor.tenantId(), department, sha256, allowed, now)) {
      if (!department.equals(row.departmentId())
          || !"ACTIVE".equals(row.status())
          || row.expiresAt() == null
          || !row.expiresAt().isAfter(now)
          || row.snapshotVersion() != 1) continue;
      try {
        HrAccessPolicy.requireFor(
            actor, "hr:candidate:read", department, row.candidateId(), "CANDIDATE");
      } catch (HrBusinessException denied) {
        if (denied.status() == 403 || denied.status() == 404) continue;
        throw denied;
      }
      Set<String> purposes =
          row.purposes() == null
              ? Set.of()
              : new HashSet<>(Arrays.asList(row.purposes().split(",")));
      if (!purposes.contains("RECRUITMENT") && !purposes.contains("TALENT_POOL")) continue;
      try {
        Facts facts = json.readValue(codec.open(row.factsJson()), Facts.class);
        JsonNode extraction = json.readTree(codec.open(row.extractionJson()));
        if (facts.version() != 1
            || !row.candidateId().equals(facts.candidateId())
            || !extension(filename).equals(extension(facts.filename()))
            || !extraction.isObject()) continue;
        return new Reuse(facts, extraction);
      } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
        throw new HrBusinessException("HR_REUSE_SNAPSHOT_INVALID", "原始解析快照无法验证", 503);
      }
    }
    return null;
  }

  private static String extension(String filename) {
    if (filename == null || filename.lastIndexOf('.') < 0) return "";
    return filename.substring(filename.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
  }
}
