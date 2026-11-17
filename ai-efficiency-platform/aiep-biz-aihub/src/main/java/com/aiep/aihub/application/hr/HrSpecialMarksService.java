package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.repository.hr.*;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 五标记始终计算，展示开关绝不参与评分；重复比较只读取当前授权来源。 */
@Service
public class HrSpecialMarksService {
  private final HrTalentMapper factsMapper;
  private final com.fasterxml.jackson.databind.ObjectMapper json;
  private final HrSpecialMarksMapper mapper;
  private final HrTalentSearchService talent;
  private final HrTalentIdentityMapper identities;
  private final HrSensitiveJsonCodec codec;
  private final HrAuditService audit;

  public HrSpecialMarksService(
      HrTalentMapper factsMapper,
      com.fasterxml.jackson.databind.ObjectMapper json,
      HrSpecialMarksMapper mapper,
      HrTalentSearchService talent,
      HrTalentIdentityMapper identities,
      HrSensitiveJsonCodec codec,
      HrAuditService audit) {
    this.factsMapper = factsMapper;
    this.json = json;
    this.mapper = mapper;
    this.talent = talent;
    this.identities = identities;
    this.codec = codec;
    this.audit = audit;
  }

  public static List<SpecialMark> basic(
      Facts facts,
      List<HardConditionView> hard,
      List<String> reasons,
      String band,
      List<String> visible) {
    boolean manual =
        facts.qualityScore() == null
            || facts.qualityScore() < 85
            || facts.fields().stream().anyMatch(f -> "NEEDS_REVIEW".equals(f.status()))
            || reasons.stream()
                .anyMatch(
                    r ->
                        Set.of(
                                "CRITICAL_REQUIREMENT_UNKNOWN",
                                "HARD_CONDITION_UNVERIFIED",
                                "DIMENSION_UNKNOWN",
                                "EVIDENCE_COVERAGE_LOW",
                                "INSUFFICIENT_COVERAGE",
                                "STRONG_COVERAGE_REQUIRED",
                                "INSUFFICIENT_COVERAGE",
                                "EVIDENCE_CONFLICT")
                            .contains(r))
            || hard.stream().anyMatch(h -> Set.of("UNKNOWN", "NEEDS_REVIEW").contains(h.status()));
    boolean borderline = hard.stream().anyMatch(h -> "BORDERLINE".equals(h.status()));
    boolean quality =
        facts.fields().stream()
                .anyMatch(
                    f -> Set.of("CONFLICT", "INVALID", "QUALITY_WARNING").contains(f.status()))
            || facts.structuredFacts().stream().anyMatch(HrSpecialMarksService::reversedDate)
            || reasons.contains("EVIDENCE_CONFLICT")
            || facts.fields().stream()
                .anyMatch(
                    f ->
                        f.reason() != null
                            && List.of("时间冲突", "日期矛盾", "隐藏指令", "文本结构异常", "OCR低可靠").stream()
                                .anyMatch(f.reason()::contains));
    boolean background =
        Set.of("REVIEW", "NOT_RECOMMEND").contains(Objects.toString(band, ""))
            && facts.structuredFacts().stream()
                .anyMatch(
                    f ->
                        Set.of("ENTREPRENEURSHIP", "CAREER_TRANSITION")
                                .contains(Objects.toString(f.backgroundClaim(), ""))
                            && validEvidence(f, facts));
    return List.of(
        mark("MANUAL_REVIEW", manual, visible, "低置信或关键事实待核验"),
        mark("BORDERLINE", borderline, visible, "硬条件处于已配置容差范围"),
        mark("QUALITY_WARNING", quality, visible, "存在可观察的时间或字段结构冲突"),
        mark("DUPLICATE", false, visible, "未发现当前授权来源中的未确认重复"),
        mark("SPECIAL_BACKGROUND", background, visible, "有来源支持的明确跨界或创业事实，低档结果仅供关注，不调整分数"));
  }

  public List<SpecialMark> calculate(
      HrActor actor,
      Facts facts,
      List<HardConditionView> hard,
      List<String> reasons,
      String band,
      List<String> visible) {
    List<SpecialMark> result = new ArrayList<>(basic(facts, hard, reasons, band, visible));
    if (actor == null) return List.copyOf(result);
    var current = talent.authorized(actor, facts.candidateId(), "hr:candidate:read");
    String text = visibleText(facts);
    boolean duplicate = false;
    Set<String> suggested = new HashSet<>();
    for (var association : identities.associations(actor.tenantId(), current.id()))
      if ("SUGGESTED".equals(association.status()))
        suggested.add(
            association.primaryCandidateId().equals(current.id())
                ? association.sourceCandidateId()
                : association.primaryCandidateId());
    var candidates = talent.visibleCandidates(actor, "hr:candidate:read", Instant.now());
    var batch = talent.factsBatch(actor, candidates);
    for (var other : candidates) {
      if (other.id().equals(current.id())) continue;
      Facts otherFacts = batch.get(other.id()).facts();
      var pair =
          pair(actor.tenantId(), current.id(), facts.version(), other.id(), otherFacts.version());
      if (mapper.distinct(pair)) continue;
      if (suggested.contains(other.id())
          || HrTalentDedup.similarity(text, visibleText(otherFacts)) >= 0.85) {
        duplicate = true;
        break;
      }
    }
    result.set(
        3,
        mark(
            "DUPLICATE",
            duplicate,
            visible,
            duplicate ? "当前授权范围内存在未确认不同人的相似来源或身份建议；不自动合并" : "未发现当前授权来源中的未确认重复"));
    return List.copyOf(result);
  }

  public List<SpecialMark> project(HrActor actor, Matching matching) {
    if (matching.specialMarks().isEmpty()) return List.of();
    var snapshot = factsMapper.snapshot(actor.tenantId(), matching.factSnapshotId());
    if (snapshot == null) throw HrTalentSearchService.missing();
    try {
      Facts facts = json.readValue(codec.open(snapshot.factsJson()), Facts.class);
      var visible =
          matching.specialMarks().stream()
              .filter(SpecialMark::visible)
              .map(SpecialMark::key)
              .toList();
      var fresh =
          calculate(
              actor,
              facts,
              matching.hardConditions(),
              matching.reasonCodes(),
              matching.band(),
              visible);
      return matching.specialMarks().stream()
          .map(mark -> mark.key().equals("DUPLICATE") ? fresh.get(3) : mark)
          .toList();
    } catch (com.fasterxml.jackson.core.JsonProcessingException error) {
      throw new HrBusinessException("HR_FACT_CONTRACT_FAILED", "事实快照无法验证", 503);
    }
  }

  @Transactional
  public void confirmDistinct(HrActor actor, String id, DistinctConfirmation request) {
    HrCandidateMergeService.reason(request.reason());
    if (id.equals(request.otherCandidateId())) throw HrTalentSearchService.invalid();
    var a = talent.authorized(actor, id, "hr:candidate:merge");
    var b = talent.authorized(actor, request.otherCandidateId(), "hr:candidate:merge");
    var af = talent.facts(actor, a);
    var bf = talent.facts(actor, b);
    if (af.version() != request.expectedFactVersion() || bf.version() != request.otherFactVersion())
      throw HrCandidateMergeService.conflict();
    mapper.confirm(
        pair(actor.tenantId(), id, af.version(), b.id(), bf.version()),
        actor.userId(),
        codec.seal(request.reason()),
        Instant.now());
    audit.append(actor, "CANDIDATES_CONFIRMED_DISTINCT", id, a.departmentId());
  }

  private static HrSpecialMarksMapper.Pair pair(
      String tenant, String a, long av, String b, long bv) {
    return a.compareTo(b) < 0
        ? new HrSpecialMarksMapper.Pair(tenant, a, b, av, bv)
        : new HrSpecialMarksMapper.Pair(tenant, b, a, bv, av);
  }

  private static String visibleText(Facts facts) {
    return new InterviewViewAssembler()
        .resume(facts).stream()
            .map(HrInterviewContracts.ResumeSection::text)
            .collect(java.util.stream.Collectors.joining("\n"));
  }

  private static boolean validEvidence(StructuredFact f, Facts facts) {
    if (f.evidence() == null || f.evidence().isEmpty()) return false;
    return f.evidence().stream()
        .anyMatch(
            e ->
                facts.blocks().stream()
                    .anyMatch(
                        b -> {
                          int[] p = b.text().codePoints().toArray();
                          return b.id().equals(e.blockId())
                              && e.start() >= 0
                              && e.end() > e.start()
                              && e.end() <= p.length
                              && new String(p, e.start(), e.end() - e.start()).equals(e.quote());
                        }));
  }

  private static boolean reversedDate(StructuredFact f) {
    if (f.startDate() == null || f.endDate() == null) return false;
    try {
      String a = f.startDate().value(), b = f.endDate().value();
      if (a == null || b == null) return false;
      String left = a.length() == 4 ? a + "-01" : a.substring(0, 7),
          right = b.length() == 4 ? b + "-12" : b.substring(0, 7);
      return java.time.YearMonth.parse(left).isAfter(java.time.YearMonth.parse(right));
    } catch (RuntimeException e) {
      return false;
    }
  }

  private static SpecialMark mark(String key, boolean active, List<String> visible, String reason) {
    return new SpecialMark(
        key, active, visible == null || visible.contains(key), active ? reason : "未触发");
  }
}
