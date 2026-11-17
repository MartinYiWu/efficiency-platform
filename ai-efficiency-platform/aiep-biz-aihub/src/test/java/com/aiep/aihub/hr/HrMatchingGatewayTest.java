package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.platformai.api.*;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingGatewayTest {
  final AiInvokeFacade facade = mock(AiInvokeFacade.class);
  final ObjectMapper json = new ObjectMapper();
  final HrSemanticGateway gateway = new HrSemanticGateway(facade, json);
  final HrActor actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:matching:run"));

  @Test
  void logicalOperationIsStableAcrossGatewayRecreationAndEnvelopeMutation() throws Exception {
    List<String> operations = new ArrayList<>();
    List<com.fasterxml.jackson.databind.JsonNode> scopes = new ArrayList<>();
    when(facade.executeSkill(any()))
        .thenAnswer(
            invocation -> {
              AiSkillExecuteRequest request = invocation.getArgument(0);
              var input = json.readTree(request.input());
              operations.add(input.get("operation_id").asText());
              scopes.add(input.path("memory_context").path("scope"));
              var output =
                  json.createObjectNode()
                      .put("contract_version", "hr-result/1")
                      .put("skill", "hr.requirements.evaluate")
                      .put("run_id", input.get("run_id").asText())
                      .put("operation_id", input.get("operation_id").asText());
              output.putObject("data").putArray("assessments");
              return new AiTextResponse(output.toString());
            });
    var input = json.createObjectNode().put("candidate_ref", "c");
    input.putObject("memory_context").put("untrusted", true);
    gateway.execute(actor, 6103, "run", input);
    new HrSemanticGateway(facade, json).execute(actor, 6103, "run", input);
    assertEquals(operations.getFirst(), operations.getLast());
    for (var scope : scopes) {
      assertEquals("t", scope.path("tenant_id").asText());
      assertEquals("1", scope.path("user_id").asText());
      assertEquals("hr", scope.path("domain").asText());
      assertEquals("hr", scope.path("top_level_agent_id").asText());
      assertEquals("TASK_ONLY", scope.path("session_kind").asText());
      assertTrue(scope.path("session_id").isNull());
    }
  }

  @Test
  void paidGateCodeSurvivesFacadeBoundary() {
    when(facade.executeSkill(any()))
        .thenThrow(new AiInvocationException(402, "PAID_BUDGET_EXHAUSTED", "safe"));
    HrBusinessException error =
        assertThrows(
            HrBusinessException.class,
            () -> gateway.execute(actor, 6103, "run", json.createObjectNode()));
    assertEquals("PAID_BUDGET_EXHAUSTED", error.code());
    assertEquals(402, error.status());
  }

  @Test
  void downstreamFailureDoesNotConfirmCancellation() {
    when(facade.executeSkill(any()))
        .thenThrow(new AiInvocationException(503, "AGENT_UNAVAILABLE", "safe"));
    assertFalse(gateway.cancel(actor, "run"));
  }
}
