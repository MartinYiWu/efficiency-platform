package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class HrBatchBudgetServiceTest {
  @Test
  void whole_batch_plan_freezes_same_budget_and_shared_item_scope_before_any_paid_generation() {
    var mapper = mock(HrBatchBudgetMapper.class);
    var gateway = mock(HrSemanticGateway.class);
    var json = new ObjectMapper().findAndRegisterModules();
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload"));
    when(gateway.execute(eq(actor), eq(6109L), anyString(), any()))
        .thenReturn(
            json.createObjectNode()
                .put("ready", true)
                .put("budget_ref", "fixed")
                .put("plan_ref", "a".repeat(64))
                .put("maximum_cost_microunits", 510)
                .put("deadline_epoch_ms", Instant.now().plusSeconds(100).toEpochMilli()));
    var service = new HrBatchBudgetService(mapper, gateway, json);
    var item =
        new HrBatchMapper.ItemRow(
            "item",
            "t",
            "batch",
            "synthetic.txt",
            "sealed",
            "hash",
            "PENDING",
            null,
            null,
            null,
            0);
    var plan = service.plan(actor, "batch", "d", List.of(item), "MATCH");
    assertEquals(51, plan.maxCalls());
    assertEquals(List.of("hr-import-item"), plan.runRefs());
    var input = ArgumentCaptor.forClass(com.fasterxml.jackson.databind.node.ObjectNode.class);
    verify(gateway).execute(eq(actor), eq(6109L), eq("hr-batch-plan-batch"), input.capture());
    assertEquals(17, input.getValue().path("workload").size());
    assertEquals(
        1,
        input.getValue().path("workload").findValuesAsText("run_ref").stream().distinct().count());
    var row = ArgumentCaptor.forClass(HrBatchBudgetMapper.Row.class);
    verify(mapper).insert(row.capture());
    when(mapper.find("t", "batch")).thenReturn(row.getValue());
    assertEquals("fixed", service.validate(actor, "batch").budgetRef());
  }

  @Test
  void absent_budget_or_replacement_budget_does_not_write_plan() {
    var mapper = mock(HrBatchBudgetMapper.class);
    var gateway = mock(HrSemanticGateway.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload"));
    var json = new ObjectMapper().findAndRegisterModules();
    when(gateway.execute(eq(actor), eq(6109L), anyString(), any()))
        .thenThrow(new HrBusinessException("NO_BUDGET", "none", 409));
    var item =
        new HrBatchMapper.ItemRow(
            "item",
            "t",
            "batch",
            "synthetic.txt",
            "sealed",
            "hash",
            "PENDING",
            null,
            null,
            null,
            0);
    assertThrows(
        HrBusinessException.class,
        () ->
            new HrBatchBudgetService(mapper, gateway, json)
                .plan(actor, "batch", "d", List.of(item), "STORE_ONLY"));
    verify(mapper, never()).insert(any());
  }

  @Test
  void frozen_one_attempt_policy_changes_all_workload_bounds() {
    var mapper = mock(HrBatchBudgetMapper.class);
    var gateway = mock(HrSemanticGateway.class);
    var limits = mock(HrBatchLimits.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload"));
    var json = new ObjectMapper().findAndRegisterModules();
    when(limits.get(actor, "batch"))
        .thenReturn(new HrBatchLimits.Limits(20971520, 104857600, 100, 1));
    when(gateway.execute(eq(actor), eq(6109L), anyString(), any()))
        .thenReturn(
            json.createObjectNode()
                .put("ready", true)
                .put("budget_ref", "fixed")
                .put("plan_ref", "a".repeat(64))
                .put("maximum_cost_microunits", 17)
                .put("deadline_epoch_ms", Instant.now().plusSeconds(100).toEpochMilli()));
    var service = new HrBatchBudgetService(mapper, gateway, json, null, null, limits);
    var item =
        new HrBatchMapper.ItemRow(
            "item",
            "t",
            "batch",
            "synthetic.txt",
            "sealed",
            "hash",
            "PENDING",
            null,
            null,
            null,
            0);
    assertEquals(17, service.plan(actor, "batch", "d", List.of(item), "MATCH").maxCalls());
    var payload = ArgumentCaptor.forClass(com.fasterxml.jackson.databind.node.ObjectNode.class);
    verify(gateway).execute(eq(actor), eq(6109L), anyString(), payload.capture());
    for (var operation : payload.getValue().path("workload"))
      assertEquals(1, operation.path("attempts").asInt());
  }
}
