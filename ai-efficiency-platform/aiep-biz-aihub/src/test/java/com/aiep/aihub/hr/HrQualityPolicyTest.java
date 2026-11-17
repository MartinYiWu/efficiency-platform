package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.application.hr.HrQualityPolicy;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrQualityPolicyTest {
  @Test
  void unresolved_dictionary_item_is_not_an_evidence_conflict() {
    var facts =
        new com.aiep.aihub.api.hr.HrCandidateContracts.Facts(
            "c",
            "r",
            "r.txt",
            0,
            90,
            "CONFIRMED",
            new com.aiep.aihub.api.hr.HrCandidateContracts.Profile("合成", null, null, null),
            List.of(),
            List.of(
                new com.aiep.aihub.api.hr.HrCandidateContracts.Field(
                    "f", "language", "未归一", "NEEDS_REVIEW", "词典未归一或存在歧义", List.of())),
            List.of(),
            0,
            1,
            1);
    assertFalse(HrQualityPolicy.hasEvidenceConflict(facts));
  }

  @Test
  void missingNameAlwaysPauses() {
    assertTrue(
        HrQualityPolicy.evaluate(
                Map.of(
                    "name",
                    0,
                    "employment",
                    100,
                    "project",
                    100,
                    "skill",
                    100,
                    "education",
                    100,
                    "other",
                    100),
                Set.of(),
                0)
            .requiresConfirmation());
  }

  @Test
  void exactWeightedQualityAndGates() {
    var q =
        HrQualityPolicy.evaluate(
            Map.of(
                "name",
                100,
                "employment",
                60,
                "project",
                100,
                "skill",
                100,
                "education",
                100,
                "other",
                100),
            Set.of(),
            2);
    assertEquals(88, q.score());
    assertTrue(q.requiresConfirmation());
  }

  @Test
  void explicitNotApplicableRenormalizesRatherThanBecomingZero() {
    var q =
        HrQualityPolicy.evaluate(
            Map.of(
                "name",
                100,
                "employment",
                100,
                "project",
                100,
                "skill",
                100,
                "education",
                100,
                "other",
                0),
            Set.of("other"),
            0);
    assertEquals(100, q.score());
    assertFalse(q.requiresConfirmation());
  }
}
