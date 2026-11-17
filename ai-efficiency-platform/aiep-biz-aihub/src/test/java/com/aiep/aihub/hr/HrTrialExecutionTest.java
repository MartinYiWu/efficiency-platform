package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrTrialContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrSettingsRepository;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTrialExecutionTest {
  final HrSettingsRepository repository = mock(HrSettingsRepository.class);
  final HrPositionService positions = mock(HrPositionService.class);
  final HrCandidateService candidates = mock(HrCandidateService.class);
  final HrTrialEvaluator evaluator = mock(HrTrialEvaluator.class);
  final HrActor actor =
      new HrActor(
          "t", "1", Set.of("d"), Set.of("hr:trial:run", "hr:trial:read", "hr:candidate:read"));
  final Map<String, Object> stored = new HashMap<>();
  final HrTrialService service = new HrTrialService(repository, positions, candidates, evaluator);

  HrTrialExecutionTest() {
    when(repository.exists(any(), anyString(), anyString()))
        .thenAnswer(i -> stored.containsKey(i.getArgument(1) + ":" + i.getArgument(2)));
    when(repository.get(any(), anyString(), anyString(), any()))
        .thenAnswer(i -> stored.get(i.getArgument(1) + ":" + i.getArgument(2)));
    doAnswer(
            i -> {
              String key = i.getArgument(1) + ":" + i.getArgument(2);
              Object old = stored.get(key);
              long expected = i.getArgument(4);
              long actual =
                  old instanceof Trial t
                      ? t.version()
                      : old instanceof ExecutionPlan p ? p.version() : old == null ? 0 : 1;
              if (actual != expected)
                throw new HrBusinessException("HR_VERSION_CONFLICT", "conflict", 409);
              stored.put(key, i.getArgument(6));
              return null;
            })
        .when(repository)
        .save(
            any(), anyString(), anyString(), anyString(), anyLong(), anyLong(), any(), anyString());
    var draft = new HrMatchingLifecycleTest().config().snapshot();
    stored.put(
        "TRIAL:trial",
        new Trial(
            "trial",
            "p",
            "d",
            10,
            1,
            7,
            "hash",
            1,
            "BLOCKED_NEEDS_EVALUATION",
            List.of(
                new TrialResult(
                    "c",
                    "BLOCKED_NEEDS_EVALUATION",
                    null,
                    null,
                    null,
                    List.of(),
                    "s",
                    "HR_TRIAL_BUDGET_REQUIRED")),
            List.of(),
            null,
            null,
            false,
            draft,
            LocalDate.now()));
  }

  @Test
  void no_budget_rejects_whole_plan_without_running_or_faking_candidate_label() {
    when(evaluator.preflight(eq(actor), eq("trial"), any()))
        .thenThrow(new HrBusinessException("NO_BUDGET", "no budget", 409));
    var plan = service.plan(actor, "trial", new PlanRequest(1));
    assertEquals("BUDGET_REJECTED", plan.status());
    assertEquals("NO_BUDGET", plan.errorCode());
    assertEquals(3, plan.maximumNewHttpAttempts());
    assertThrows(
        HrBusinessException.class,
        () -> service.execute(actor, "trial", new ExecuteRequest(1, plan.version())));
    verify(evaluator, never())
        .execute(
            any(), anyString(), any(), any(), anyString(), anyString(), any(), any(), any(), any());
    assertNull(service.get(actor, "trial").results().getFirst().label());
  }

  @Test
  void explicit_execution_claims_stable_scope_once_and_stores_only_sandbox() {
    var check =
        JsonMapper.builder()
            .build()
            .createObjectNode()
            .put("ready", true)
            .put("budget_ref", "fixed-budget")
            .put("plan_ref", "a".repeat(64))
            .put("maximum_cost_microunits", 300);
    when(evaluator.preflight(eq(actor), eq("trial"), any())).thenReturn(check);
    when(evaluator.preflight(eq(actor), eq("trial"), any(), eq("fixed-budget"), eq("a".repeat(64))))
        .thenReturn(check);
    var plan = service.plan(actor, "trial", new PlanRequest(1));
    when(evaluator.execute(
            eq(actor),
            eq("c"),
            any(),
            any(),
            eq(plan.operations().getFirst().runRef()),
            eq("s"),
            any(),
            any(),
            any(),
            any()))
        .thenReturn(
            new TrialResult(
                "c",
                "SUCCEEDED",
                "RECOMMENDED",
                BigDecimal.valueOf(75),
                BigDecimal.valueOf(100),
                List.of(),
                "s",
                null));
    var result = service.execute(actor, "trial", new ExecuteRequest(1, plan.version()));
    assertEquals("COMPLETED", result.status());
    assertNull(result.results().getFirst().label());
    assertThrows(
        HrBusinessException.class,
        () -> service.execute(actor, "trial", new ExecuteRequest(1, plan.version())));
    verify(evaluator, times(1))
        .execute(
            any(), anyString(), any(), any(), anyString(), anyString(), any(), any(), any(), any());
    assertEquals(1, stored.keySet().stream().filter(k -> k.startsWith("TRIAL_ITEM:")).count());
  }

  @Test
  void unknown_failed_submission_does_not_get_a_new_scope_or_automatic_retry() {
    var check =
        JsonMapper.builder()
            .build()
            .createObjectNode()
            .put("ready", true)
            .put("budget_ref", "fixed-budget")
            .put("plan_ref", "a".repeat(64));
    when(evaluator.preflight(eq(actor), eq("trial"), any())).thenReturn(check);
    when(evaluator.preflight(eq(actor), eq("trial"), any(), eq("fixed-budget"), eq("a".repeat(64))))
        .thenReturn(check);
    var plan = service.plan(actor, "trial", new PlanRequest(1));
    when(evaluator.execute(
            any(), anyString(), any(), any(), anyString(), anyString(), any(), any(), any(), any()))
        .thenThrow(new HrBusinessException("PROVIDER_PAYMENT_REQUIRED", "payment", 402));
    var trial = service.execute(actor, "trial", new ExecuteRequest(1, plan.version()));
    assertEquals("BLOCKED_EXECUTION", trial.status());
    assertNull(trial.results().getFirst().label());
    assertEquals("SYSTEM_FAILED", trial.results().getFirst().status());
    assertThrows(
        HrBusinessException.class,
        () -> service.plan(actor, "trial", new PlanRequest(trial.version())));
    verify(evaluator, times(1))
        .execute(
            any(), anyString(), any(), any(), anyString(), anyString(), any(), any(), any(), any());
  }
}
