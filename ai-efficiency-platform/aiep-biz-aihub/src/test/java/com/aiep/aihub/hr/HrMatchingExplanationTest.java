package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.HrMatchingService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingExplanationTest {
  final ObjectMapper json = new ObjectMapper();
  final Block block = new Block("b", null, "使用Java", null);
  final SemanticAssessment match =
      new SemanticAssessment("r", "MATCH", "有项目证据", List.of(new Evidence("b", 0, 6, "使用Java")));

  @Test
  void acceptsOnlyQuotedEvidenceForConfirmedRequirement() throws Exception {
    var data =
        json.readTree(
            "{\"highlights\":[{\"text\":\"存在Java使用证据\",\"evidence\":[{\"block_id\":\"b\",\"start\":0,\"end\":6,\"quote\":\"使用Java\"}],\"requirement_ids\":[\"r\"]}],\"gaps\":[]}");
    assertEquals(
        "COMPLETE",
        HrMatchingService.validateExplanation(data, List.of(match), List.of(block)).status());
  }

  @Test
  void cannotExplainUnknownAsPositive() throws Exception {
    var data =
        json.readTree(
            "{\"highlights\":[{\"text\":\"满足\",\"evidence\":[{\"block_id\":\"b\",\"start\":0,\"end\":6,\"quote\":\"使用Java\"}],\"requirement_ids\":[\"r\"]}],\"gaps\":[]}");
    assertThrows(
        RuntimeException.class,
        () ->
            HrMatchingService.validateExplanation(
                data,
                List.of(new SemanticAssessment("r", "UNKNOWN", "未确定", List.of())),
                List.of(block)));
  }

  @Test
  void cannotInventEvidenceEvenWhenBlockExists() throws Exception {
    var data =
        json.readTree(
            "{\"highlights\":[{\"text\":\"满足\",\"evidence\":[{\"block_id\":\"b\",\"start\":2,\"end\":6,\"quote\":\"Java\"}],\"requirement_ids\":[\"r\"]}],\"gaps\":[]}");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateExplanation(data, List.of(match), List.of(block)));
  }

  @Test
  void acceptsGroundedVerificationAndRejectsInventedSummaryOrAlteredCitation() throws Exception {
    var data = json.createObjectNode();
    data.putArray("highlights");
    data.putArray("gaps");
    data.put("summary", "使用Java");
    var item = data.putArray("verification_points").addObject().put("text", "请核实职责范围");
    item.putArray("requirement_ids").add("r");
    item.putArray("evidence")
        .addObject()
        .put("block_id", "b")
        .put("start", 0)
        .put("end", 6)
        .put("quote", "使用Java");
    data.putArray("quality_notes");
    var result = HrMatchingService.validateExplanation(data, List.of(match), List.of(block));
    assertEquals(1, result.verificationPoints().size());
    assertTrue(result.qualityNotes().isEmpty());
    assertEquals("使用Java", result.summary());
    data.put("summary", "管理100人团队");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateExplanation(data, List.of(match), List.of(block)));
    data.put("summary", "使用Java");
    ((com.fasterxml.jackson.databind.node.ObjectNode) item.path("evidence").get(0))
        .put("quote", "伪造引用");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateExplanation(data, List.of(match), List.of(block)));
  }

  @Test
  void legacyResponseDoesNotInventSummaryOrVerificationPoints() throws Exception {
    var result =
        HrMatchingService.validateExplanation(
            json.readTree("{\"highlights\":[],\"gaps\":[]}"), List.of(), List.of());
    assertEquals("", result.summary());
    assertTrue(result.verificationPoints().isEmpty());
    assertTrue(result.qualityNotes().isEmpty());
    var data =
        json.readTree("{\"highlights\":[],\"gaps\":[],\"summary\":\"" + "字".repeat(81) + "\"}");
    assertThrows(
        RuntimeException.class,
        () -> HrMatchingService.validateExplanation(data, List.of(match), List.of(block)));
  }
}
