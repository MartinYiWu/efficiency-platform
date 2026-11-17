package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.HrMatchingService;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Status;
import java.math.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrLanguageSemanticTest {
  private HardRule rule(String unit, String expected, BigDecimal tolerance) {
    return new HardRule(
        "lang",
        "LANGUAGE",
        "语言等级",
        expected,
        unit,
        BigDecimal.valueOf(4),
        tolerance,
        true,
        List.of(expected),
        "ALL");
  }

  @Test
  void cefr_b1_is_borderline_for_frozen_b2_tolerance_one() {
    var rule = rule("CEFR", "B2", BigDecimal.ONE);
    assertEquals(
        Status.BORDERLINE,
        HrMatchingService.semanticHardStatus(
            rule,
            new HrAtomicAssessment(
                "lang", HrAtomicAssessment.Level.PARTIAL_MATCH, null, null, List.of("b"))));
    assertEquals(
        Status.FAIL,
        HrMatchingService.semanticHardStatus(
            rule("CEFR", "B2", BigDecimal.ZERO),
            new HrAtomicAssessment(
                "lang", HrAtomicAssessment.Level.PARTIAL_MATCH, null, null, List.of("b"))));
  }

  @Test
  void jlpt_n1_matches_frozen_n2_anchor_without_numeric_reversal() {
    assertEquals(
        Status.PASS,
        HrMatchingService.semanticHardStatus(
            rule("JLPT", "N2", BigDecimal.ZERO),
            new HrAtomicAssessment(
                "lang", HrAtomicAssessment.Level.MATCH, null, null, List.of("b"))));
  }

  @Test
  void missing_language_remains_unknown() {
    assertEquals(
        Status.UNKNOWN,
        HrMatchingService.semanticHardStatus(
            rule("CEFR", "B2", BigDecimal.ONE),
            new HrAtomicAssessment(
                "lang", HrAtomicAssessment.Level.UNKNOWN, null, null, List.of())));
  }

  @Test
  void legacy_expected_is_one_all_atom_and_prompt_requires_explicit_system_rules() {
    var rule =
        new HardRule(
            "lang",
            "LANGUAGE",
            "语言等级",
            "CEFR B2",
            "CEFR",
            null,
            BigDecimal.ONE,
            true,
            List.of(),
            null);
    assertEquals(List.of("CEFR B2"), HrMatchingService.semanticHardValues(rule));
    assertEquals("ALL", HrMatchingService.semanticHardMode(rule));
    var anchor =
        new SemanticCriterion(
            "lang",
            "CEFR",
            "SKILL",
            "CEFR A1<A2<B1<B2<C1<C2",
            "C1/C2",
            "B2",
            "B1为容差档",
            "A1/A2",
            false);
    String text = HrMatchingService.semanticHardText(rule, anchor, "CEFR B2");
    assertTrue(text.contains("跨考试"));
    assertTrue(text.contains("仅可返回UNKNOWN"));
    assertTrue(text.contains("UNKNOWN"));
  }

  @Test
  void trial_plan_language_atom_and_score_atom_share_exact_count_and_frozen_date() {
    var source = new HrMatchingLifecycleTest().config().snapshot();
    var language =
        new HardRule(
            "lang",
            "LANGUAGE",
            "CEFR",
            "CEFR B2",
            "CEFR",
            null,
            BigDecimal.ONE,
            true,
            List.of(),
            null);
    var anchor =
        new SemanticCriterion(
            "lang",
            "CEFR",
            "SKILL",
            "CEFR A1<A2<B1<B2<C1<C2",
            "C1/C2",
            "B2",
            "B1为容差档",
            "A1/A2",
            false);
    var criteria = new java.util.ArrayList<SemanticCriterion>(source.criteria());
    criteria.add(anchor);
    var draft =
        new Draft(
            source.positionId(),
            source.name(),
            source.family(),
            source.departmentId(),
            source.level(),
            source.jdText(),
            source.lastStep(),
            source.scoring(),
            List.of(language),
            criteria,
            source.version());
    var plan = com.aiep.aihub.application.hr.HrTrialEvaluator.plan(draft);
    assertEquals(List.of("lang"), plan.hardAtoms().get("lang"));
    assertEquals(2, plan.requirements().size());
    assertTrue(
        HrMatchingService.semanticAtDate(
                plan.requirements().get("lang"), java.time.LocalDate.of(2026, 11, 11))
            .contains("2026-11-11"));
    var shared =
        new HardRule(
            "r", "REQUIRED_SKILL", "Java", "Java", null, null, null, true, List.of("Java"), "ALL");
    var dedup =
        new Draft(
            source.positionId(),
            source.name(),
            source.family(),
            source.departmentId(),
            source.level(),
            source.jdText(),
            source.lastStep(),
            source.scoring(),
            List.of(shared),
            source.criteria(),
            source.version());
    assertEquals(
        1, com.aiep.aihub.application.hr.HrTrialEvaluator.plan(dedup).requirements().size());
  }
  @Test
  void legacy_missing_or_invalid_level_configuration_remains_unknown_despite_match() {
    var anchor = new SemanticCriterion("lang", "CEFR", "SKILL", "CEFR A1<A2<B1<B2<C1<C2", "C1/C2", "B2", "B1为容差档", "A1/A2", false);
    for (BigDecimal threshold : Arrays.asList(null, BigDecimal.ONE, new BigDecimal("4.5"))) {
      var legacy = new HardRule("lang", "LANGUAGE", "语言等级", "B2", "CEFR", threshold, BigDecimal.ONE, true, List.of("B2"), "ALL");
      assertEquals(Status.UNKNOWN, HrMatchingService.semanticHardStatus(legacy,
          new HrAtomicAssessment("lang", HrAtomicAssessment.Level.MATCH, null, null, List.of("b")), anchor));
      assertTrue(HrMatchingService.semanticHardText(legacy, anchor, "B2").contains("仅可返回UNKNOWN"));
    }
  }}
