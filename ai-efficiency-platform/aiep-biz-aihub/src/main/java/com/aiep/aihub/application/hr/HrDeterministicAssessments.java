package com.aiep.aihub.application.hr;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrAtomicAssessment.Level;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;

/** 将已确认且有来源的事实接入固定公式，不从自由文本猜测指标或数值。 */
public final class HrDeterministicAssessments {
  private HrDeterministicAssessments() {}

  public static void validate(SemanticCriterion criterion) {
    Calculation c = criterion.calculation();
    if (c == null) return;
    String dimension =
        switch (c.type()) {
          case "EXPERIENCE_MONTHS" -> "EXPERIENCE";
          case "EDUCATION_RANK" -> "EDUCATION";
          case "PROJECT_SCALE", "PROJECT_ROLE", "TEAM_SIZE" -> "PROJECT";
          case "BONUS_DECLARATION" -> "BONUS";
          default -> throw HrPositionService.invalid("不支持的确定性子规则");
        };
    if (!dimension.equals(criterion.dimension())) throw HrPositionService.invalid("子规则与评分维度不一致");
    if (c.type().equals("EXPERIENCE_MONTHS")) {
      if (c.minimum() == null
          || c.maximum() == null
          || c.minimum().signum() <= 0
          || c.maximum().compareTo(c.minimum()) < 0
          || c.minimum().stripTrailingZeros().scale() > 0
          || c.maximum().stripTrailingZeros().scale() > 0)
        throw HrPositionService.invalid("理想年限须为正整数月区间");
    } else if (!c.type().equals("BONUS_DECLARATION")) {
      if (c.expected() == null || c.expected().signum() <= 0)
        throw HrPositionService.invalid("期望指标必须为正");
      if (Set.of("EDUCATION_RANK", "PROJECT_ROLE", "TEAM_SIZE").contains(c.type())
          && c.expected().stripTrailingZeros().scale() > 0)
        throw HrPositionService.invalid("等级和人数必须为整数");
      if (c.type().equals("EDUCATION_RANK") && c.expected().compareTo(BigDecimal.valueOf(5)) > 0
          || c.type().equals("PROJECT_ROLE") && c.expected().compareTo(BigDecimal.valueOf(3)) > 0)
        throw HrPositionService.invalid("等级超出允许范围");
      if (c.type().equals("PROJECT_SCALE")
          && (c.metric() == null || c.metric().isBlank() || c.unit() == null || c.unit().isBlank()))
        throw HrPositionService.invalid("项目规模必须声明指标和单位");
    }
  }

  public static HrAtomicAssessment evaluate(
      SemanticCriterion criterion, Facts facts, LocalDate date) {
    Calculation c = Objects.requireNonNull(criterion.calculation());
    Set<String> confirmed = new HashSet<>();
    for (Field f : facts.fields()) if ("CONFIRMED".equals(f.status())) confirmed.add(f.id());
    List<StructuredFact> usable =
        facts.structuredFacts().stream()
            .filter(
                f ->
                    confirmed.contains(f.factId())
                        && f.evidence() != null
                        && !f.evidence().isEmpty())
            .toList();
    BigDecimal score = null, base = null;
    List<String> evidence = new ArrayList<>();
    boolean conflict = false;
    switch (c.type()) {
      case "EXPERIENCE_MONTHS" -> {
        var bounds = HrFactMeasurements.experience(facts.structuredFacts(), facts.fields(), date);
        if (bounds != null) {
          var range =
              HrScoreEngine.experienceScore(
                  bounds.minMonths(),
                  bounds.maxMonths(),
                  c.minimum().longValueExact(),
                  c.maximum().longValueExact());
          conflict = bounds.needsReview() || range.uniqueScore() == null;
          score = conflict ? null : range.uniqueScore();
          if (score != null)
            base =
                bounds.minMonths() > c.maximum().longValueExact() ? BigDecimal.valueOf(100) : score;
          usable.stream()
              .filter(f -> "employment".equals(f.kind()) && !Boolean.TRUE.equals(f.isInternship()))
              .flatMap(f -> f.evidence().stream())
              .map(Evidence::blockId)
              .distinct()
              .limit(5)
              .forEach(evidence::add);
        }
      }
      case "EDUCATION_RANK" -> {
        var fact = HrFactMeasurements.education(usable, facts.fields());
        if (fact != null) {
          score =
              HrScoreEngine.ordinalScore(
                  HrFactMeasurements.educationRank(fact.degree()), c.expected().intValueExact());
          addEvidence(evidence, fact);
        }
      }
      case "PROJECT_SCALE", "PROJECT_ROLE", "TEAM_SIZE" -> {
        List<StructuredFact> measured =
            usable.stream()
                .filter(
                    f ->
                        "project".equals(f.kind())
                            && f.measurement() != null
                            && Objects.equals(f.factId(), f.measurement().projectId()))
                .toList();
        for (var fact : measured) {
          Measurement m = fact.measurement();
          BigDecimal value = null;
          if (c.type().equals("PROJECT_SCALE")
              && Objects.equals(c.metric(), m.metric())
              && Objects.equals(c.unit(), m.unit()))
            value = HrScoreEngine.scaleScore(m.value(), c.expected());
          if (c.type().equals("PROJECT_ROLE") && m.roleLevel() != null)
            value = HrScoreEngine.ordinalScore(m.roleLevel(), c.expected().intValueExact());
          if (c.type().equals("TEAM_SIZE") && m.managedTeamSize() != null)
            value = HrScoreEngine.scaleScore(BigDecimal.valueOf(m.managedTeamSize()), c.expected());
          if (value != null && (score == null || value.compareTo(score) > 0)) {
            score = value;
            evidence.clear();
            addEvidence(evidence, fact);
          }
        }
      }
      case "BONUS_DECLARATION" -> {
        // 命中必须是已确认的标准项，不以未出现当作明确不满足。
        var item =
            usable.stream()
                .filter(
                    f ->
                        Set.of("skill", "certificate", "language").contains(f.kind())
                            && f.value().equals(criterion.criterion()))
                .findFirst();
        if (item.isPresent()) {
          score = BigDecimal.valueOf(100);
          addEvidence(evidence, item.get());
        }
      }
      default -> throw HrPositionService.invalid("不支持的确定性子规则");
    }
    if (score == null || evidence.isEmpty())
      return new HrAtomicAssessment(
          criterion.id(), conflict ? Level.NEEDS_REVIEW : Level.UNKNOWN, null, null, List.of());
    Level level =
        score.signum() == 0
            ? Level.EXPLICIT_NOT_MET
            : score.compareTo(BigDecimal.valueOf(100)) >= 0
                ? Level.STRONG_MATCH
                : score.compareTo(BigDecimal.valueOf(80)) >= 0 ? Level.MATCH : Level.PARTIAL_MATCH;
    return new HrAtomicAssessment(criterion.id(), level, score, base, List.copyOf(evidence));
  }

  public static Map<String, HrAtomicAssessment> evaluateAll(
      List<SemanticCriterion> criteria, Facts facts, LocalDate date) {
    // 项目维度选择一项完整项目后统一计算，不能拼接各项目的最高单项。
    var projectCriteria =
        criteria.stream()
            .filter(
                c ->
                    c.calculation() != null
                        && Set.of("PROJECT_SCALE", "PROJECT_ROLE", "TEAM_SIZE")
                            .contains(c.calculation().type()))
            .toList();
    Facts selected = facts;
    BigDecimal bestCoverage = BigDecimal.valueOf(-1), bestScore = BigDecimal.valueOf(-1);
    for (var project :
        facts.structuredFacts().stream()
            .filter(f -> "project".equals(f.kind()))
            .sorted(Comparator.comparing(StructuredFact::factId))
            .toList()) {
      var scoped =
          new Facts(
              facts.candidateId(),
              facts.resumeVersionId(),
              facts.filename(),
              facts.pageCount(),
              facts.qualityScore(),
              facts.status(),
              facts.profile(),
              facts.blocks(),
              facts.fields(),
              facts.skills(),
              facts.confirmedCount(),
              facts.totalCount(),
              facts.version(),
              List.of(project));
      BigDecimal coverage = BigDecimal.ZERO, total = BigDecimal.ZERO;
      for (var c : projectCriteria) {
        var a = evaluate(c, scoped, date);
        if (a.effectiveScore() != null) {
          coverage = coverage.add(BigDecimal.ONE);
          total = total.add(a.effectiveScore());
        }
      }
      if (coverage.compareTo(bestCoverage) > 0
          || coverage.compareTo(bestCoverage) == 0 && total.compareTo(bestScore) > 0) {
        selected = scoped;
        bestCoverage = coverage;
        bestScore = total;
      }
    }
    Map<String, HrAtomicAssessment> result = new HashMap<>();
    for (var c : criteria)
      if (c.calculation() != null)
        result.put(c.id(), evaluate(c, projectCriteria.contains(c) ? selected : facts, date));
    return result;
  }

  private static void addEvidence(List<String> ids, StructuredFact fact) {
    fact.evidence().stream().map(Evidence::blockId).distinct().limit(5).forEach(ids::add);
  }
}
