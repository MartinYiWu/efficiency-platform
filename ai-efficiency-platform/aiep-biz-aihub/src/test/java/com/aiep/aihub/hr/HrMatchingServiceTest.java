package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.Block;
import com.aiep.aihub.application.hr.HrMatchingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingServiceTest {
  final ObjectMapper json = new ObjectMapper();

  @Test
  void knownAssessmentRequiresExactQuote() throws Exception {
    var data =
        json.readTree(
            "{\"assessments\":[{\"requirement_id\":\"r\",\"reason\":\"合成原因\",\"status\":\"MATCH\",\"evidence\":[{\"block_id\":\"b\",\"start\":0,\"end\":2,\"quote\":\"xx\"}]}]}");
    assertThrows(
        RuntimeException.class,
        () ->
            HrMatchingService.validateAssessments(
                data, Set.of("r"), List.of(new Block("b", null, "abc", null))));
  }

  @Test
  void unknownIsAllowedWithoutEvidence() throws Exception {
    var data =
        json.readTree(
            "{\"assessments\":[{\"requirement_id\":\"r\",\"reason\":\"合成原因\",\"status\":\"UNKNOWN\",\"evidence\":[]}]}");
    assertNull(
        HrMatchingService.validateAssessments(data, Set.of("r"), List.of())
            .get("r")
            .effectiveScore());
  }

  @Test
  void missingOrExtraRequirementsAreRejected() throws Exception {
    var data = json.readTree("{\"assessments\":[]}");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateAssessments(data, Set.of("r"), List.of()));
  }

  @Test
  void modelCannotDeclareNotApplicable() throws Exception {
    var data =
        json.readTree(
            "{\"assessments\":[{\"requirement_id\":\"r\",\"reason\":\"合成原因\",\"status\":\"NOT_APPLICABLE\",\"evidence\":[]}]}");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateAssessments(data, Set.of("r"), List.of()));
  }

  @Test
  void confirmedEducationUsesLocalOrdinalAndConfiguredTolerance() {
    var source =
        new com.aiep.aihub.api.hr.HrCandidateContracts.StructuredFact(
            "edu", "education", "本科", List.of(), null, null, "本科", null, null, null, null, null);
    var facts =
        new com.aiep.aihub.api.hr.HrCandidateContracts.Facts(
            "c",
            "r",
            "synthetic",
            0,
            null,
            "CONFIRMED",
            new com.aiep.aihub.api.hr.HrCandidateContracts.Profile("测试", null, null, null),
            List.of(),
            List.of(
                new com.aiep.aihub.api.hr.HrCandidateContracts.Field(
                    "edu", "education", "本科", "CONFIRMED", null, List.of())),
            List.of(),
            1,
            1,
            1,
            List.of(source));
    var rule =
        new com.aiep.aihub.api.hr.HrPositionContracts.HardRule(
            "h",
            "EDUCATION",
            "学历",
            "硕士",
            "level",
            java.math.BigDecimal.valueOf(4),
            java.math.BigDecimal.ONE,
            true,
            List.of(),
            null);
    assertEquals(
        com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Status.BORDERLINE,
        HrMatchingService.numericCondition(rule, facts, java.time.LocalDate.of(2026, 11, 11))
            .status());
  }

  @Test
  void unconfirmedEducationCannotBecomeKnownMeasurement() {
    var source =
        new com.aiep.aihub.api.hr.HrCandidateContracts.StructuredFact(
            "edu", "education", "本科", List.of(), null, null, "本科", null, null, null, null, null);
    var facts =
        new com.aiep.aihub.api.hr.HrCandidateContracts.Facts(
            "c",
            "r",
            "synthetic",
            0,
            null,
            "NEEDS_REVIEW",
            new com.aiep.aihub.api.hr.HrCandidateContracts.Profile("测试", null, null, null),
            List.of(),
            List.of(),
            List.of(),
            0,
            0,
            1,
            List.of(source));
    var rule =
        new com.aiep.aihub.api.hr.HrPositionContracts.HardRule(
            "h",
            "EDUCATION",
            "学历",
            "本科",
            "level",
            java.math.BigDecimal.valueOf(3),
            java.math.BigDecimal.ZERO,
            true,
            List.of(),
            null);
    assertEquals(
        com.aiep.aihub.domain.hr.HrHardConditionEvaluator.Status.UNKNOWN,
        HrMatchingService.numericCondition(rule, facts, java.time.LocalDate.of(2026, 11, 11))
            .status());
  }
}
