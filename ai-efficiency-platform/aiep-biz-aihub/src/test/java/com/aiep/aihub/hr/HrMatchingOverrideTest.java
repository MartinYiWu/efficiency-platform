package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingOverrideTest {
  final HrMatchingLifecycleTest fixture = new HrMatchingLifecycleTest();
  final HrActor actor =
      new HrActor(
          "t",
          "1",
          Set.of("d"),
          Set.of(
              "hr:matching:read",
              "hr:matching:run",
              "hr:matching:override",
              "hr:candidate:read",
              "hr:position:read"));
  final List<HrAtomicAssessment> assessments =
      List.of(
          new HrAtomicAssessment(
              "r", HrAtomicAssessment.Level.STRONG_MATCH, null, null, List.of("b")));

  String encode(Object value) throws Exception {
    return fixture.codec.seal(fixture.json.writeValueAsString(value));
  }

  Matching existing(String type, boolean allowed) throws Exception {
    ConfigVersion original = fixture.config();
    Draft d = original.snapshot();
    var hardRule =
        new HardRule(
            "h",
            type,
            "合成门槛",
            "本科",
            "level",
            java.math.BigDecimal.valueOf(3),
            java.math.BigDecimal.ZERO,
            allowed,
            List.of("Java"),
            "ALL");
    var draft =
        new Draft(
            d.positionId(),
            d.name(),
            d.family(),
            d.departmentId(),
            d.level(),
            d.jdText(),
            d.lastStep(),
            d.scoring(),
            List.of(hardRule),
            d.criteria(),
            d.version());
    var config = new ConfigVersion("cfg", "p", "v1.0", "ctx-1", draft, "hash", "1", Instant.now());
    var hard =
        List.of(new Result("h", Type.valueOf(type), Status.FAIL, allowed, "EXPLICIT_FAILURE"));
    var score =
        new HrScoreEngine()
            .score(
                d.scoring(),
                new HrVerifiedFacts(hard, false),
                assessments,
                Set.of(),
                LocalDate.of(2026, 11, 11));
    Matching result =
        new HrResultAssembler()
            .assemble(
                "old", fixture.facts(), "s", fixture.position(), config, "sem", score, assessments);
    when(fixture.repository.result("t", "old"))
        .thenReturn(
            new ResultSnapshot(
                "old",
                "t",
                "c",
                "p",
                "s",
                "v1.0",
                "ctx-1",
                "sem",
                encode(result),
                "CURRENT",
                null,
                result.createdAt(),
                result.businessStatus()));
    when(fixture.positions.get(actor, "p")).thenReturn(fixture.position());
    when(fixture.candidates.snapshot(actor, "c"))
        .thenReturn(new Snapshot("s", "t", "c", "r", 1, "sealed", "1", Instant.now().toString()));
    when(fixture.candidates.decode(any())).thenReturn(fixture.facts());
    when(fixture.repository.semantic("t", "sem"))
        .thenReturn(
            new SemanticSnapshot(
                "sem",
                "t",
                "c",
                "s",
                encode(config),
                encode(new SemanticAssessments(assessments, List.of())),
                encode(hard),
                Instant.now().toString()));
    when(fixture.repository.replaceCurrent(eq("t"), eq("old"), any())).thenReturn(true);
    return result;
  }

  @Test
  void grantingOverrideProducesNewResultAndCapsRecommendationAtReview() throws Exception {
    Matching old = existing("EDUCATION", true);
    Matching next =
        fixture.service.override(
            actor, "old", new OverrideRequest(List.of("h"), "合成资料人工复核原因", old.snapshotHash()));
    assertNotEquals("old", next.resultId());
    assertEquals("REVIEW", next.band());
    assertEquals("OVERRIDDEN", next.hardConditions().getFirst().status());
    assertEquals("GRANTED", next.overrides().getFirst().action());
    verify(fixture.gateway, never()).execute(any(), anyLong(), anyString(), any());
  }

  @Test
  void requiredSkillsHaveNoOverrideBackdoor() throws Exception {
    Matching old = existing("REQUIRED_SKILL", false);
    assertThrows(
        HrBusinessException.class,
        () ->
            fixture.service.override(
                actor, "old", new OverrideRequest(List.of("h"), "不能放行", old.snapshotHash())));
    verify(fixture.repository, never()).replaceCurrent(anyString(), anyString(), any());
  }

  @Test
  void wrongSnapshotHashAndMissingReasonAreRejected() throws Exception {
    Matching old = existing("EDUCATION", true);
    assertThrows(
        HrBusinessException.class,
        () ->
            fixture.service.override(
                actor, "old", new OverrideRequest(List.of("h"), "原因", "stale")));
    assertThrows(
        HrBusinessException.class,
        () ->
            fixture.service.override(
                actor, "old", new OverrideRequest(List.of("h"), " ", old.snapshotHash())));
  }

  @Test
  void revocationCreatesNewFailureResultWithoutChangingOriginalFact() throws Exception {
    Matching old = existing("EDUCATION", true);
    Matching granted =
        fixture.service.override(
            actor, "old", new OverrideRequest(List.of("h"), "人工复核", old.snapshotHash()));
    when(fixture.repository.result("t", granted.resultId()))
        .thenReturn(
            new ResultSnapshot(
                granted.resultId(),
                "t",
                "c",
                "p",
                "s",
                "v1.0",
                "ctx-1",
                "sem",
                encode(granted),
                "CURRENT",
                null,
                granted.createdAt(),
                granted.businessStatus()));
    when(fixture.repository.replaceCurrent(eq("t"), eq(granted.resultId()), any()))
        .thenReturn(true);
    Matching revoked =
        fixture.service.revokeOverride(
            actor,
            granted.resultId(),
            new RevokeOverrideRequest(
                granted.overrides().getFirst().id(), "复核后撤销", granted.snapshotHash()));
    assertEquals("FILTERED", revoked.businessStatus());
    assertNull(revoked.totalScore());
    assertEquals(2, revoked.overrides().size());
    assertEquals("REVOKED", revoked.overrides().getLast().action());
    assertEquals("FAIL", revoked.hardConditions().getFirst().status());
  }

  @Test
  void separateOverridePermissionIsMandatory() {
    HrActor unprivileged =
        new HrActor("t", "1", Set.of("d"), Set.of("hr:matching:read", "hr:matching:run"));
    assertThrows(
        HrBusinessException.class,
        () ->
            fixture.service.override(
                unprivileged, "old", new OverrideRequest(List.of("h"), "原因", "hash")));
    verifyNoInteractions(fixture.repository);
  }

  @Test
  void explicitlyPublishedSkillOverrideStillRequiresPermissionAndCapsAtReview() throws Exception {
    Matching old = existing("REQUIRED_SKILL", true);
    Matching next =
        fixture.service.override(
            actor, "old", new OverrideRequest(List.of("h"), "授权岗位配置允许的例外", old.snapshotHash()));
    assertEquals("REVIEW", next.band());
    assertEquals("OVERRIDDEN", next.hardConditions().getFirst().status());
  }
}
