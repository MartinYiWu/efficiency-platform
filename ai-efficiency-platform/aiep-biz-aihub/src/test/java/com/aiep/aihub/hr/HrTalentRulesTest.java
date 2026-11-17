package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class HrTalentRulesTest {
  @Test
  void full_casefold_preserves_dotless_i_and_expands_sharp_s() {
    assertEquals(1d, com.aiep.aihub.application.hr.HrTalentDedup.similarity("Straße", "STRASSE"));
    assertEquals(0d, com.aiep.aihub.application.hr.HrTalentDedup.similarity("ı", "I"));
    assertEquals(1d, com.aiep.aihub.application.hr.HrTalentDedup.similarity("ς", "σ"));
  }

  @Test
  void empty_and_unicode_dedup_are_symmetric() throws Exception {
    var type = Class.forName("com.aiep.aihub.application.hr.HrTalentDedup");
    var method = type.getMethod("similarity", String.class, String.class);
    assertEquals(0d, method.invoke(null, "", ""));
    assertEquals(1d, method.invoke(null, "Ａ B\u200BＣ", "abc"));
    assertEquals(
        method.invoke(null, "招聘工程师 Java", "Java招聘工程师"),
        method.invoke(null, "Java招聘工程师", "招聘工程师 Java"));
  }

  @Test
  void presets_respect_frozen_six_layer_counts() throws Exception {
    var type = Class.forName("com.aiep.aihub.application.hr.HrInterviewRules");
    assertArrayEquals(
        new int[] {4, 3, 2, 4, 3, 1}, (int[]) type.getMethod("preset", int.class).invoke(null, 60));
    assertEquals(
        58,
        type.getMethod("estimated", int[].class, int[].class)
            .invoke(null, new int[] {4, 3, 2, 4, 3, 1}, new int[] {3, 3, 3, 4, 4, 3}));
  }
}
