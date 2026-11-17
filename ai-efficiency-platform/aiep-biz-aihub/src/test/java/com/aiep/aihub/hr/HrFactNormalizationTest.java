package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrDictionaryContracts.*;
import com.aiep.aihub.application.hr.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrFactNormalizationTest {
  @Test
  void one_frozen_dictionary_preserves_original_and_separate_standard_identity() {
    var service = mock(HrDictionaryService.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload"));
    when(service.publishedForUpload(actor, "d"))
        .thenReturn(
            new com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary(
                "d",
                "PUBLISHED",
                List.of(new Entry("java-id", "SKILL", "Java", List.of("JDK"), "")),
                7));
    var fact =
        new StructuredFact(
            "f",
            "skill",
            "JDK",
            List.of(new Evidence("b", 0, 3, "JDK")),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null);
    var unknown =
        new StructuredFact(
            "unknown",
            "skill",
            "Other",
            List.of(new Evidence("b2", 0, 5, "Other")),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null);
    var result =
        new HrFactNormalization(service)
            .normalize(
                actor,
                "d",
                List.of(fact, unknown),
                List.of(new Block("b", null, "JDK", null), new Block("b2", null, "Other", null)));
    assertEquals(7, result.dictionaryVersion());
    assertEquals("JDK", fact.value());
    var normalized = result.normalizations().getFirst();
    assertEquals("java-id", normalized.standardId());
    assertEquals("Java", normalized.canonical());
    assertEquals(100, normalized.quality());
    assertEquals(60, result.normalizations().get(1).quality());
    verify(service, times(1)).publishedForUpload(actor, "d");
  }

  @Test
  void correction_reuses_only_exact_frozen_dictionary_and_null_does_not_select_latest() {
    var dictionary = mock(HrDictionaryService.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:correct"));
    var service = new HrFactNormalization(dictionary);
    var empty = service.normalizeFrozen(actor, "d", List.of(), List.of(), null);
    assertNull(empty.dictionaryVersion());
    assertTrue(empty.normalizations().isEmpty());
    verifyNoInteractions(dictionary);
    when(dictionary.publishedForCorrection(actor, "d", 7L))
        .thenReturn(
            new com.aiep.aihub.api.hr.HrDictionaryContracts.Dictionary(
                "d",
                "PUBLISHED",
                List.of(new Entry("old-java-id", "SKILL", "Java", List.of("JDK"), "")),
                7));
    var fact =
        new StructuredFact(
            "f",
            "skill",
            "JDK",
            List.of(new Evidence("b", 0, 3, "JDK")),
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null);
    var result =
        service.normalizeFrozen(
            actor, "d", List.of(fact), List.of(new Block("b", null, "JDK", null)), 7L);
    assertEquals(7L, result.dictionaryVersion());
    assertEquals("old-java-id", result.normalizations().getFirst().standardId());
    verify(dictionary, never()).publishedForUpload(any(), anyString());
  }
}
