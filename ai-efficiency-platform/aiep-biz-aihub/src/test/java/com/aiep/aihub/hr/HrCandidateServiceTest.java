package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrCandidateServiceTest {
  @Test
  void rejectsMissingEvidence() {
    assertThrows(
        RuntimeException.class, () -> HrCandidateService.validateEvidence("abc", 0, 2, "zz"));
  }

  @Test
  void acceptsCodepointOffsetsAfterSupplementaryUnicode() {
    assertDoesNotThrow(() -> HrCandidateService.validateEvidence("😀Java", 1, 5, "Java"));
    assertThrows(
        RuntimeException.class, () -> HrCandidateService.validateEvidence("😀Java", 2, 6, "Java"));
  }

  @Test
  void acceptsExactEvidence() {
    assertDoesNotThrow(() -> HrCandidateService.validateEvidence("abc", 0, 2, "ab"));
  }

  final HrCandidateRepositoryPort repository = mock(HrCandidateRepositoryPort.class);
  final HrSensitiveJsonCodec codec =
      new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));
  final HrCandidateService service =
      new HrCandidateService(repository, new ObjectMapper(), codec, mock(HrSemanticGateway.class));
  final HrActor actor =
      new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:read", "hr:candidate:correct"));

  Facts old() {
    return new Facts(
        "c",
        "r",
        "synthetic.txt",
        0,
        null,
        "NEEDS_REVIEW",
        new Profile("合成测试", null, null, null),
        List.of(new Block("b", null, "合成测试技能", null)),
        List.of(new Field("f", "skill", "技能", "NEEDS_REVIEW", null, List.of("b"))),
        List.of(),
        0,
        1,
        1);
  }

  void existing() {
    when(repository.find("t", "c")).thenReturn(new Candidate("c", "t", "d", "s1", 1));
    when(repository.snapshot("t", "s1"))
        .thenReturn(
            new Snapshot(
                "s1", "t", "c", "r", 1, service.encode(old()), "1", "2026-11-11T00:00:00Z"));
  }

  @Test
  void correctionCreatesNewEncryptedSnapshotAndInvalidatesResults() {
    existing();
    when(repository.advance(eq("t"), eq("c"), anyString(), eq(1L))).thenReturn(true);
    Facts next =
        service.correct(
            actor, "c", new Corrections(1, List.of(new Correction("f", "已核实技能", "人工核对合成来源"))));
    assertEquals(2, next.version());
    assertEquals("CONFIRMED", next.fields().getFirst().status());
    assertEquals(2, next.blocks().size());
    verify(repository).staleResults("t", "c");
    verify(repository)
        .insertSnapshot(argThat(s -> s.version() == 2 && !s.factsJson().contains("已核实技能")));
  }

  @Test
  void staleVersionCannotWriteOrInvalidate() {
    existing();
    assertThrows(
        HrBusinessException.class,
        () ->
            service.correct(
                actor, "c", new Corrections(0, List.of(new Correction("f", "新值", "理由")))));
    verify(repository, never()).insertSnapshot(any());
    verify(repository, never()).staleResults(anyString(), anyString());
  }

  @Test
  void unavailableDepartmentNeverReturnsFacts() {
    when(repository.find("t", "c")).thenReturn(new Candidate("c", "t", "other", "s1", 1));
    assertThrows(HrBusinessException.class, () -> service.facts(actor, "c"));
    verify(repository, never()).snapshot(anyString(), anyString());
  }

  @Test
  void confirmationAllowsDefaultReason() {
    existing();
    when(repository.advance(eq("t"), eq("c"), anyString(), eq(1L))).thenReturn(true);
    Facts next = service.confirm(actor, "c", new Confirmations(1, List.of("f"), null));
    assertEquals(1, next.confirmedCount());
    assertNotNull(next.fields().getFirst().reason());
  }
}
