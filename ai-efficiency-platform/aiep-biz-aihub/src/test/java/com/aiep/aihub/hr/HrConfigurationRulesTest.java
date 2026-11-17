package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrDictionaryContracts.*;
import com.aiep.aihub.api.hr.HrSettingsContracts.*;
import com.aiep.aihub.application.hr.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrConfigurationRulesTest {
  @Test
  void settings_rejects_escalation_and_invalid_boundaries() {
    Settings d = HrSettingsService.defaults("d");
    assertEquals(12, d.retentionMonths());
    assertThrows(
        RuntimeException.class,
        () ->
            HrSettingsService.validate(
                new Settings(
                    "d", "DRAFT", 61, 3, 3, 30, 80, 65, 50, "v1", 20971520, 104857600, 100, 1,
                    List.of()),
                d));
    assertThrows(
        RuntimeException.class,
        () ->
            HrSettingsService.validate(
                new Settings(
                    "d", "DRAFT", 12, 3, 3, 30, 80, 65, 50, "v1", 20971521, 104857600, 100, 1,
                    List.of()),
                d));
  }

  @Test
  void dictionary_conflicts_are_reported_atomically() {
    assertFalse(
        HrDictionaryService.conflicts(
                List.of(
                    new Entry("a", "SKILL", "Java", List.of("JVM"), ""),
                    new Entry("b", "SKILL", "Kotlin", List.of("JVM"), "")))
            .isEmpty());
    assertTrue(
        HrDictionaryService.conflicts(
                List.of(
                    new Entry("a", "SKILL", "Java", List.of("JVM"), "Java"),
                    new Entry("b", "SKILL", "Kotlin", List.of("JVM"), "Kotlin")))
            .isEmpty());
  }

  @Test
  void diagnosis_respects_priority_and_empty_results() {
    assertEquals("NO_VALID_RESULTS", HrTrialService.diagnose(List.of()));
    assertEquals(
        "HARD_CONDITIONS_TOO_STRICT",
        HrTrialService.diagnose(List.of("FILTERED", "FILTERED", "RECOMMENDED")));
    assertEquals(
        "SCORING_TOO_LENIENT",
        HrTrialService.diagnose(List.of("STRONGLY_RECOMMENDED", "RECOMMENDED")));
  }

  @Test
  void context_conflict_never_chooses_an_arbitrary_dictionary_answer() {
    assertFalse(
        HrDictionaryService.conflicts(
                List.of(
                    new Entry("a", "SKILL", "Java", List.of("JVM"), "服务"),
                    new Entry("b", "SKILL", "Kotlin", List.of("JVM"), "服务")))
            .isEmpty());
  }

  @Test
  void nine_platform_templates_have_exact_weights() {
    assertEquals(9, HrTemplateService.platformTemplates().size());
    assertTrue(
        HrTemplateService.platformTemplates().stream()
            .allMatch(
                t ->
                    t.system()
                        && t.weights().values().stream().mapToInt(Integer::intValue).sum() == 100));
  }
}
