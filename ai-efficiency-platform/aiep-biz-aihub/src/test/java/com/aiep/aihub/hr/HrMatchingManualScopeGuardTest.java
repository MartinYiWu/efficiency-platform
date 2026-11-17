package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.Run;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingManualScopeGuardTest {
  @Test
  void cancelled_manual_scope_is_rejected_before_provider_without_old_batch_lookup()
      throws Exception {
    var facade = mock(AiInvokeFacade.class);
    var json = new ObjectMapper().findAndRegisterModules();
    var plans = mock(HrMatchingExecutionPlanMapper.class);
    var runs = mock(HrMatchingMapper.class);
    var batches = mock(HrBatchMapper.class);
    var gateway =
        new HrSemanticGateway(
            facade,
            json,
            null,
            mock(HrBatchBudgetMapper.class),
            batches,
            mock(HrExecutionMapper.class),
            plans,
            runs,
            mock(HrCandidateMapper.class),
            mock(HrPositionMapper.class),
            mock(HrSourceAuthorization.class));
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:matching:run"));
    String scope = "hr-match-stable";
    var plan =
        new HrMatchingExecutionPlans.Plan(
            "run", scope, "budget", "plan", Instant.now().plusSeconds(600), 2, 4, 100, false);
    when(plans.find("t", scope))
        .thenReturn(
            new HrMatchingExecutionPlanMapper.Row(
                "t", scope, "run", json.writeValueAsString(plan)));
    when(runs.run("t", "run"))
        .thenReturn(
            new Run(
                "run",
                "t",
                "c",
                "p",
                "CANCEL_PENDING",
                null,
                null,
                Instant.now(),
                "cipher",
                Instant.now().plusSeconds(600),
                "key",
                "hash",
                scope));
    assertEquals(
        "HR_RUN_CANCELLED",
        assertThrows(
                HrBusinessException.class,
                () -> gateway.execute(actor, 6103, scope, json.createObjectNode()))
            .code());
    verifyNoInteractions(facade);
    verify(batches, never()).item(any(), any());
  }
}
