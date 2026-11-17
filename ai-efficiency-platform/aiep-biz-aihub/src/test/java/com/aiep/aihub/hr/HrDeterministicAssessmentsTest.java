package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.HrDeterministicAssessments;
import com.aiep.aihub.domain.hr.HrAtomicAssessment;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrDeterministicAssessmentsTest {
  final LocalDate date = LocalDate.of(2026, 11, 11);

  SemanticCriterion criterion(
      String type, String min, String max, String expected, String metric, String unit) {
    return new SemanticCriterion(
        "r",
        "标准",
        "EXPERIENCE",
        "标准",
        "强",
        "满足",
        "部分",
        "不足",
        false,
        new Calculation(type, decimal(min), decimal(max), decimal(expected), metric, unit));
  }

  static BigDecimal decimal(String v) {
    return v == null ? null : new BigDecimal(v);
  }

  StructuredFact fact(
      String id,
      String kind,
      String degree,
      DateValue start,
      DateValue end,
      Measurement measurement) {
    return new StructuredFact(
        id,
        kind,
        "合成事实",
        List.of(new Evidence("b", 0, 4, "合成事实")),
        null,
        null,
        degree,
        null,
        start,
        end,
        false,
        false,
        measurement);
  }

  Facts facts(StructuredFact... facts) {
    return new Facts(
        "c",
        "v",
        "synthetic.txt",
        0,
        100,
        "CONFIRMED",
        new Profile("合成人", null, null, null),
        List.of(new Block("b", null, "合成事实", null)),
        Arrays.stream(facts)
            .map(f -> new Field(f.factId(), f.kind(), f.value(), "CONFIRMED", null, List.of("b")))
            .toList(),
        List.of(),
        facts.length,
        facts.length,
        1,
        List.of(facts));
  }

  @Test
  void educationIsOrdinalRatherThanModelLevel() {
    var a =
        HrDeterministicAssessments.evaluate(
            criterion("EDUCATION_RANK", null, null, "3", null, null),
            facts(fact("e", "education", "硕士", null, null, null)),
            date);
    assertEquals(new BigDecimal("100"), a.effectiveScore());
  }

  @Test
  void experienceUsesUnionAndOverqualificationBase() {
    var f =
        fact(
            "w",
            "employment",
            null,
            new DateValue("2016-01", "MONTH", "2016-01"),
            new DateValue("2025-12", "MONTH", "2025-12"),
            null);
    var a =
        HrDeterministicAssessments.evaluate(
            criterion("EXPERIENCE_MONTHS", "24", "60", null, null, "month"),
            facts(f, fact("w2", "employment", null, f.startDate(), f.endDate(), null)),
            date);
    assertEquals(new BigDecimal("60.0"), a.effectiveScore());
    assertEquals(new BigDecimal("100"), a.baseScore());
  }

  @Test
  void uncertainExperienceDoesNotSelectConvenientEndpoint() {
    var f =
        fact(
            "w",
            "employment",
            null,
            new DateValue("2020", "YEAR", "2020"),
            new DateValue("2022", "YEAR", "2022"),
            null);
    var a =
        HrDeterministicAssessments.evaluate(
            criterion("EXPERIENCE_MONTHS", "36", "60", null, null, "month"), facts(f), date);
    assertEquals(HrAtomicAssessment.Level.NEEDS_REVIEW, a.level());
    assertNull(a.effectiveScore());
  }

  @Test
  void scaleUsesSameMetricAndUnitOnly() {
    var f =
        fact(
            "p",
            "project",
            null,
            null,
            null,
            new Measurement("QPS", "request/second", new BigDecimal("1250"), "p", null, null));
    var a =
        HrDeterministicAssessments.evaluate(
            criterion("PROJECT_SCALE", null, null, "1000", "QPS", "request/second"),
            facts(f),
            date);
    assertEquals(new BigDecimal("100"), a.effectiveScore());
    assertEquals(
        HrAtomicAssessment.Level.UNKNOWN,
        HrDeterministicAssessments.evaluate(
                criterion("PROJECT_SCALE", null, null, "1000", "DAU", "user/day"), facts(f), date)
            .level());
  }

  @Test
  void absentEvidenceNeverTurnsIntoZero() {
    assertEquals(
        HrAtomicAssessment.Level.UNKNOWN,
        HrDeterministicAssessments.evaluate(
                criterion("EDUCATION_RANK", null, null, "3", null, null), facts(), date)
            .level());
  }

  @Test
  void projectDimensionCannotSpliceBestScaleAndBestRole() {
    var scale = criterion("PROJECT_SCALE", null, null, "1000", "QPS", "request/second");
    var role =
        new SemanticCriterion(
            "role",
            "角色",
            "PROJECT",
            "角色",
            "强",
            "满足",
            "部分",
            "不足",
            false,
            new Calculation("PROJECT_ROLE", null, null, new BigDecimal("3"), null, null));
    var a =
        fact(
            "p1",
            "project",
            null,
            null,
            null,
            new Measurement("QPS", "request/second", new BigDecimal("1250"), "p1", 1, null));
    var b =
        fact(
            "p2",
            "project",
            null,
            null,
            null,
            new Measurement("QPS", "request/second", new BigDecimal("100"), "p2", 3, null));
    var result = HrDeterministicAssessments.evaluateAll(List.of(scale, role), facts(a, b), date);
    assertFalse(
        result.get("r").effectiveScore().intValue() == 100
            && result.get("role").effectiveScore().intValue() == 80);
  }
}
