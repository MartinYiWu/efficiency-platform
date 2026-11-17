package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.HrTrialEvaluator;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.domain.hr.HrHardConditionEvaluator.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class HrTrialCacheDateTest {
  @ParameterizedTest @ValueSource(strings = {"LANGUAGE", "CERTIFICATE"})
  void cross_day_cannot_reuse_pass_without_authorized_evaluation(String type) throws Exception {
    var f = fixture(type);
    var date = LocalDate.of(2026, 11, 10);
    cache(f, List.of(result(f, date)));
    var actual = new HrTrialEvaluator(f.candidates, f.repository, f.json, f.codec)
        .evaluate(f.actor, "c", draft(f, type), date.plusDays(1));
    assertEquals("BLOCKED_NEEDS_EVALUATION", actual.status());
    assertNull(actual.label());
    verifyNoInteractions(f.gateway);
  }

  @ParameterizedTest @ValueSource(strings = {"LANGUAGE", "CERTIFICATE"})
  void same_day_reuses_pass_without_model(String type) throws Exception {
    var f = fixture(type);
    var date = LocalDate.of(2026, 11, 10);
    cache(f, List.of(result(f, date)));
    assertEquals("SUCCEEDED", new HrTrialEvaluator(f.candidates, f.repository, f.json, f.codec)
        .evaluate(f.actor, "c", draft(f, type), date).status());
    verifyNoInteractions(f.gateway);
  }

  @ParameterizedTest @ValueSource(strings = {"LANGUAGE", "CERTIFICATE"})
  void skips_other_date_and_continues_to_same_date(String type) throws Exception {
    var f = fixture(type);
    var date = LocalDate.of(2026, 11, 11);
    cache(f, List.of(result(f, date.minusDays(1)), result(f, date)));
    assertEquals("SUCCEEDED", new HrTrialEvaluator(f.candidates, f.repository, f.json, f.codec)
        .evaluate(f.actor, "c", draft(f, type), date).status());
    verify(f.repository, times(1)).semantic("t", "sem");
  }

  void cache(HrMatchingLifecycleTest f, List<ResultSnapshot> results) {
    when(f.repository.list(any(), any(), any(), any(), any(), any(), any(), any(), anyInt(), anyInt()))
        .thenReturn(results);
  }

  HrMatchingLifecycleTest fixture(String type) throws Exception {
    var f = new HrMatchingLifecycleTest(); f.setup();
    when(f.candidates.candidate(f.actor, "c")).thenReturn(new Candidate("c", "t", "d", "s", 1));
    var config = new ConfigVersion("cfg", "p", "v1.0", "ctx-1", draft(f, type), "hash", "1", Instant.now());
    var assessments = new SemanticAssessments(List.of(new HrAtomicAssessment("r", HrAtomicAssessment.Level.MATCH, null, null, List.of("b"))), List.of());
    var hard = List.of(new Result("h", Type.valueOf(type), Status.PASS, true, "VERIFIED"));
    when(f.repository.semantic("t", "sem")).thenReturn(new SemanticSnapshot("sem", "t", "c", "s", f.codec.seal(f.json.writeValueAsString(config)), f.codec.seal(f.json.writeValueAsString(assessments)), f.codec.seal(f.json.writeValueAsString(hard)), "2026-11-10"));
    return f;
  }

  Draft draft(HrMatchingLifecycleTest f, String type) {
    var d = f.config().snapshot();
    var criteria = new ArrayList<>(d.criteria());
    criteria.add(new SemanticCriterion("h", "有效证书", "SKILL", "同体系有效证书", "强", "有效", "容差", "失效", true));
    return new Draft(d.positionId(), d.name(), d.family(), d.departmentId(), d.level(), d.jdText(), d.lastStep(), d.scoring(), List.of(new HardRule("h", type, "有效证书", "B2", "CEFR", BigDecimal.valueOf(4), BigDecimal.ONE, true, List.of("B2"), "ALL")), criteria, d.version());
  }

  ResultSnapshot result(HrMatchingLifecycleTest f, LocalDate date) throws Exception {
    var matching = new Matching("old", "c", "合成", "p", "岗位", "s", "v1.0", "ctx-1", "sem", date.toString(), "SCORED", "COMPLETE", BigDecimal.valueOf(80), BigDecimal.valueOf(80), BigDecimal.valueOf(100), "RECOMMEND", List.of(), List.of(), List.of(), List.of(), "hash", "2026-11-10", null, List.of(), List.of(), List.of(80,65,50), 0, List.of(), null);
    return new ResultSnapshot("old", "t", "c", "p", "s", "v1.0", "ctx-1", "sem", f.codec.seal(f.json.writeValueAsString(matching)), "CURRENT", null, "2026-11-10", "SCORED");
  }
}
