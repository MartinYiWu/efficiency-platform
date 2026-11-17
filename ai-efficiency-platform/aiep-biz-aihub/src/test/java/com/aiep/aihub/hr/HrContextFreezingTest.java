package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrPositionRepository;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrContextFreezingTest {
  @Test
  void changed_jd_uses_new_context_without_changing_published_rules_or_history() {
    var repository = mock(HrPositionRepository.class);
    var contexts = mock(HrContextService.class);
    var service = new HrPositionService(repository, contexts);
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:position:read"));
    var draft =
        new Draft(
            "p", "原名", "TECHNOLOGY", "d", "P3", "旧JD", "PREVIEW", null, List.of(), List.of(), 1);
    var oldContext = new ContextSnapshot("p", "原名", "d", "P3", "旧JD", "ctx-old");
    var published =
        new ConfigVersion(
            "cfg",
            "p",
            "v1",
            "ctx-old",
            draft,
            "rules-hash",
            "u",
            Instant.now(),
            null,
            Map.of(),
            oldContext);
    var position =
        new Position(
            "p",
            "t",
            "新名",
            "TECHNOLOGY",
            "d",
            "P4",
            "code",
            "ACTIVE",
            "v1",
            "ctx-new",
            "u",
            Instant.now(),
            2);
    when(repository.find("t", "p")).thenReturn(position);
    when(contexts.get(actor, "p", "ctx-new"))
        .thenReturn(new HrContextService.Context("p", "新名", "d", "P4", "新JD", "ctx-new"));
    var frozen = service.withCurrentContext(actor, position, published);
    assertEquals("v1", frozen.version());
    assertEquals("rules-hash", frozen.snapshotHash());
    assertSame(draft, frozen.snapshot());
    assertEquals("新JD", frozen.context().jdText());
    assertEquals("P4", frozen.context().level());
    assertEquals("ctx-new", frozen.contextVersion());
    assertEquals("旧JD", published.context().jdText());
    assertEquals("ctx-old", published.contextVersion());
    verify(repository, never()).insertConfig(any(), any());
  }

  @Test
  void only_explanation_receives_new_frozen_context_and_previous_run_keeps_its_context()
      throws Exception {
    var f = new HrMatchingLifecycleTest();
    f.setup();
    var old = f.config();
    var fresh =
        new ConfigVersion(
            old.id(),
            old.positionId(),
            old.version(),
            "ctx-new",
            old.snapshot(),
            old.snapshotHash(),
            old.publishedBy(),
            old.publishedAt(),
            old.dictionaryVersion(),
            old.bindings(),
            new ContextSnapshot("p", "新名", "d", "P7", "新JD仅解释上下文", "ctx-new"));
    when(f.positions.withCurrentContext(any(), any(), any())).thenReturn(fresh);
    var pending =
        f.service.prepare(
            f.actor,
            new com.aiep.aihub.api.hr.HrCandidateContracts.MatchRequest("c", "p", 1),
            "context-test-key");
    var frozen =
        f.json.readValue(
            f.codec.open(pending.inputJson()),
            com.aiep.aihub.api.hr.HrCandidateContracts.FrozenInput.class);
    assertEquals("v1.0", frozen.config().version());
    assertEquals("新JD仅解释上下文", frozen.config().context().jdText());
    assertEquals("", old.snapshot().jdText());
    var running =
        new com.aiep.aihub.api.hr.HrCandidateContracts.Run(
            pending.id(),
            pending.tenantId(),
            pending.candidateId(),
            pending.positionId(),
            "RUNNING",
            null,
            null,
            pending.createdAt(),
            pending.inputJson(),
            pending.deadlineAt(),
            pending.idempotencyKey(),
            pending.requestHash(),
            pending.scopeRef());
    when(f.repository.run("t", pending.id())).thenReturn(running);
    when(f.repository.start("t", pending.id())).thenReturn(true);
    when(f.repository.completeRun(anyString(), anyString(), any(), any())).thenReturn(true);
    when(f.gateway.execute(eq(f.actor), eq(6103L), eq(pending.scopeRef()), any()))
        .thenAnswer(
            i -> {
              var input = (com.fasterxml.jackson.databind.node.ObjectNode) i.getArgument(3);
              assertFalse(input.has("jd_text"));
              return f.json.readTree(
                  "{\"assessments\":[{\"requirement_id\":\"r\",\"status\":\"MATCH\",\"reason\":\"明确证据\",\"evidence\":[{\"block_id\":\"b\",\"start\":0,\"end\":4,\"quote\":\"Java\"}]}]}");
            });
    when(f.gateway.execute(eq(f.actor), eq(6104L), eq(pending.scopeRef()), any()))
        .thenAnswer(
            i -> {
              var input = (com.fasterxml.jackson.databind.node.ObjectNode) i.getArgument(3);
              assertEquals("新JD仅解释上下文", input.path("jd_text").asText());
              return f.json.readTree("{\"highlights\":[],\"gaps\":[]}");
            });
    f.service.execute(
        f.actor,
        new com.aiep.aihub.api.hr.HrCandidateContracts.MatchRequest("c", "p", 1),
        pending.id());
    verify(f.gateway).execute(eq(f.actor), eq(6104L), eq(pending.scopeRef()), any());
    assertNull(old.context());
  }
}
