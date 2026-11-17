package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrBatchBudgetReuseTest {
  @Test
  void reuse_only_store_batch_needs_no_paid_authorization_or_model_calls() {
    var mapper = mock(HrBatchBudgetMapper.class);
    var gateway = mock(HrSemanticGateway.class);
    var reuse = mock(HrResumeReuseService.class);
    var json = JsonMapper.builder().findAndAddModules().build();
    var codec = new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));
    var actor =
        new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:upload", "hr:candidate:read"));
    when(reuse.find(eq(actor), eq("d"), anyString(), eq("r.txt")))
        .thenReturn(new HrResumeReuseService.Reuse(null, json.createObjectNode()));
    var item =
        new HrBatchMapper.ItemRow(
            "i",
            "t",
            "b",
            "r.txt",
            codec.seal(Base64.getEncoder().encodeToString("synthetic".getBytes())),
            "hash",
            "PENDING",
            "UPLOADED",
            null,
            null,
            0);
    var service = new HrBatchBudgetService(mapper, gateway, json, reuse, codec);
    var plan = service.plan(actor, "b", "d", List.of(item), "STORE_ONLY");
    assertEquals(0, plan.maxCalls());
    assertEquals(0, plan.maxCost());
    assertEquals("CPU_ONLY", plan.budgetRef());
    verifyNoInteractions(gateway);
  }
}
