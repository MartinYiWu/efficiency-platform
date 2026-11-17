package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import java.time.*;
import org.junit.jupiter.api.Test;

class HrMatchingPurposeCaseTest {
  @Test
  void direct_talent_matching_uses_new_stable_plan_not_old_upload_scope() {
    var f = new HrMatchingLifecycleTest();
    f.setup();
    var plans = mock(HrMatchingExecutionPlans.class);
    var sources = mock(HrSourceAuthorization.class);
    when(plans.scope(any(), anyString(), anyString(), anyString(), anyString(), anyString(), any()))
        .thenReturn("hr-match-stable");
    when(plans.prepare(eq(f.actor), anyString(), eq("hr-match-stable"), eq(1), eq(true)))
        .thenAnswer(
            i ->
                new HrMatchingExecutionPlans.Plan(
                    i.getArgument(1),
                    "hr-match-stable",
                    "new-budget",
                    "new-plan",
                    Instant.now().plusSeconds(600),
                    2,
                    4,
                    100,
                    false));
    var service =
        new HrMatchingService(
            f.candidates,
            f.positions,
            f.repository,
            f.gateway,
            new HrResultAssembler(),
            f.json,
            f.codec,
            null,
            sources,
            plans);
    var run = service.prepare(f.actor, new MatchRequest("c", "p", 1), "direct-key-1");
    assertEquals("hr-match-stable", run.scopeRef());
    verify(sources, never()).executionScope(anyString(), anyString());
    when(plans.findRun(f.actor, "hr-match-stable")).thenReturn(run);
    assertEquals(
        run.id(), service.prepare(f.actor, new MatchRequest("c", "p", 1), "changed-key-2").id());
    verify(plans, times(1)).prepare(eq(f.actor), anyString(), anyString(), anyInt(), anyBoolean());
    verify(f.repository, times(1)).insertRun(any());
  }

  @Test
  void missing_new_budget_does_not_insert_run_or_send_model() {
    var f = new HrMatchingLifecycleTest();
    f.setup();
    var plans = mock(HrMatchingExecutionPlans.class);
    when(plans.scope(any(), anyString(), anyString(), anyString(), anyString(), anyString(), any()))
        .thenReturn("hr-match-stable");
    when(plans.prepare(any(), anyString(), anyString(), anyInt(), anyBoolean()))
        .thenThrow(new HrBusinessException("NO_BUDGET", "没有有效预算", 409));
    var service =
        new HrMatchingService(
            f.candidates,
            f.positions,
            f.repository,
            f.gateway,
            new HrResultAssembler(),
            f.json,
            f.codec,
            null,
            mock(HrSourceAuthorization.class),
            plans);
    assertThrows(
        HrBusinessException.class,
        () -> service.prepare(f.actor, new MatchRequest("c", "p", 1), "direct-key-1"));
    verify(f.repository, never()).insertRun(any());
    verifyNoInteractions(f.gateway);
  }

  @Test
  void same_day_successful_old_batch_run_is_reused_before_any_new_plan() throws Exception {
    var f = new HrMatchingLifecycleTest();
    f.setup();
    var plans = mock(HrMatchingExecutionPlans.class);
    var sources = mock(HrSourceAuthorization.class);
    var input =
        new FrozenInput(new MatchRequest("c", "p", 1), f.facts(), "s", f.position(), f.config());
    String encrypted = f.codec.seal(f.json.writeValueAsString(input));
    Instant now = Instant.now();
    var old =
        new Run(
            "old-batch-run",
            "t",
            "c",
            "p",
            "SUCCEEDED",
            "result",
            null,
            now,
            encrypted,
            now.minusSeconds(1),
            "old-client-key",
            "old-hash",
            "hr-import-original-item");
    when(f.repository.recentRuns(eq("t"), eq("c"), eq("p"), any(), eq(100)))
        .thenReturn(java.util.List.of(old));
    var service =
        new HrMatchingService(
            f.candidates,
            f.positions,
            f.repository,
            f.gateway,
            new HrResultAssembler(),
            f.json,
            f.codec,
            null,
            sources,
            plans);
    var returned = service.prepare(f.actor, new MatchRequest("c", "p", 1), "new-client-key");
    assertEquals(old, returned);
    verify(plans, never()).prepare(any(), anyString(), anyString(), anyInt(), anyBoolean());
    verify(f.repository, never()).insertRun(any());
    verifyNoInteractions(f.gateway);
    var since = org.mockito.ArgumentCaptor.forClass(Instant.class);
    verify(f.repository).recentRuns(eq("t"), eq("c"), eq("p"), since.capture(), eq(100));
    assertEquals(
        java.time.LocalDate.now(ZoneId.of("Asia/Shanghai"))
            .atStartOfDay(ZoneId.of("Asia/Shanghai"))
            .toInstant(),
        since.getValue());
  }
}
