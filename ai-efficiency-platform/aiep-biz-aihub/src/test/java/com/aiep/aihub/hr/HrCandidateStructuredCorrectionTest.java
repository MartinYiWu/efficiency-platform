package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrCandidateStructuredCorrectionTest {
  final HrCandidateRepositoryPort repository = mock(HrCandidateRepositoryPort.class);
  final HrCandidateService service =
      new HrCandidateService(
          repository,
          new ObjectMapper(),
          new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32])),
          mock(HrSemanticGateway.class));
  final HrActor actor =
      new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:read", "hr:candidate:correct"));

  Facts original() {
    return new Facts(
        "c",
        "r",
        "synthetic.txt",
        0,
        null,
        "NEEDS_REVIEW",
        new Profile("合成测试", null, null, null),
        List.of(new Block("b", null, "本科，计算机专业", null)),
        List.of(new Field("edu", "education", "专科", "NEEDS_REVIEW", null, List.of("b"))),
        List.of(),
        0,
        1,
        1,
        List.of(
            new StructuredFact(
                "edu",
                "education",
                "专科",
                List.of(new Evidence("b", 0, 2, "本科")),
                null,
                null,
                "专科",
                null,
                null,
                null,
                null,
                null)));
  }

  void setup() {
    when(repository.find("t", "c")).thenReturn(new Candidate("c", "t", "d", "s", 1));
    when(repository.snapshot("t", "s"))
        .thenReturn(
            new Snapshot(
                "s", "t", "c", "r", 1, service.encode(original()), "1", "2026-11-11T00:00:00Z"));
    when(repository.advance(eq("t"), eq("c"), anyString(), eq(1L))).thenReturn(true);
  }

  @Test
  void complexFactCannotBeOverwrittenWithScalar() {
    setup();
    assertThrows(
        HrBusinessException.class,
        () ->
            service.correct(
                actor, "c", new Corrections(1, List.of(new Correction("edu", "本科", "核对证据")))));
    verify(repository, never()).insertSnapshot(any());
  }

  @Test
  void structuredCorrectionChangesFieldProfileAndSnapshotTogether() {
    setup();
    StructuredFact corrected =
        new StructuredFact(
            "edu",
            "education",
            "本科",
            List.of(new Evidence("b", 0, 2, "本科")),
            null,
            null,
            "本科",
            null,
            null,
            null,
            null,
            null);
    Facts next =
        service.correctStructured(
            actor,
            "c",
            new StructuredCorrections(
                1, List.of(new StructuredCorrection("edu", corrected, "核对原文"))));
    assertEquals("本科", next.fields().getFirst().value());
    assertEquals("本科", next.profile().education());
    assertEquals("本科", next.structuredFacts().getFirst().degree());
    assertEquals(1, next.blocks().size());
  }

  @Test
  void fabricatedStructuredValueWithoutEvidenceIsRejected() {
    setup();
    StructuredFact fake =
        new StructuredFact(
            "edu",
            "education",
            "博士",
            List.of(new Evidence("b", 0, 2, "本科")),
            null,
            null,
            "博士",
            null,
            null,
            null,
            null,
            null);
    assertThrows(
        HrBusinessException.class,
        () ->
            service.correctStructured(
                actor,
                "c",
                new StructuredCorrections(
                    1, List.of(new StructuredCorrection("edu", fake, "错误来源")))));
    verify(repository, never()).insertSnapshot(any());
  }

  @Test
  void explicitHumanSourceCanCorrectOcrWithoutPretendingItWasOriginalText() throws Exception {
    setup();
    StructuredFact corrected =
        new StructuredFact(
            "edu", "education", "博士", List.of(), null, null, "博士", null, null, null, null, null);
    ObjectMapper json = new ObjectMapper();
    com.fasterxml.jackson.databind.node.ObjectNode body =
        json.valueToTree(new StructuredCorrection("edu", corrected, "核对候选人补充的学历证明"));
    body.put("humanSource", "经人工核对候选人提供的博士学历证明，确认最高学历为博士。");
    StructuredCorrection correction = json.treeToValue(body, StructuredCorrection.class);
    Facts next =
        service.correctStructured(actor, "c", new StructuredCorrections(1, List.of(correction)));
    assertEquals("博士", next.profile().education());
    assertEquals(2, next.blocks().size());
    Block source = next.blocks().getLast();
    assertEquals("HUMAN_CORRECTION", source.section());
    assertEquals(source.id(), next.structuredFacts().getFirst().evidence().getFirst().blockId());
    assertEquals(source.text(), next.structuredFacts().getFirst().evidence().getFirst().quote());
    assertEquals("本科，计算机专业", next.blocks().getFirst().text());
    assertEquals("专科", original().structuredFacts().getFirst().degree());
  }
}
