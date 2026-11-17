package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.domain.hr.*;
import com.aiep.aihub.repository.hr.HrMatchingRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingLifecycleTest {
  final HrCandidateService candidates = mock(HrCandidateService.class);
  final HrPositionService positions = mock(HrPositionService.class);
  final HrMatchingRepository repository = mock(HrMatchingRepository.class);
  final HrSemanticGateway gateway = mock(HrSemanticGateway.class);
  final ObjectMapper json = new ObjectMapper().findAndRegisterModules();
  final HrSensitiveJsonCodec codec =
      new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));
  final HrMatchingService service =
      new HrMatchingService(
          candidates, positions, repository, gateway, new HrResultAssembler(), json, codec);
  final HrActor actor =
      new HrActor(
          "t",
          "1",
          Set.of("d"),
          Set.of("hr:matching:run", "hr:matching:read", "hr:candidate:read", "hr:position:read"));

  Position position() {
    return new Position(
        "p",
        "t",
        "合成岗位",
        "TECHNOLOGY",
        "d",
        "P6",
        "CODE",
        "ACTIVE",
        "v1.0",
        "ctx-1",
        "1",
        Instant.now(),
        1);
  }

  Facts facts() {
    return new Facts(
        "c",
        "r",
        "synthetic.txt",
        0,
        null,
        "CONFIRMED",
        new Profile("合成测试", null, null, null),
        List.of(new Block("b", null, "Java合成经历", null)),
        List.of(),
        List.of(),
        0,
        0,
        1);
  }

  ConfigVersion config() {
    var scoring =
        new HrFrozenConfig(
            "v1.0",
            Map.of(
                HrFrozenConfig.Dimension.SKILL,
                100,
                HrFrozenConfig.Dimension.EXPERIENCE,
                0,
                HrFrozenConfig.Dimension.PROJECT,
                0,
                HrFrozenConfig.Dimension.EDUCATION,
                0,
                HrFrozenConfig.Dimension.BONUS,
                0),
            List.of(
                new HrFrozenConfig.Requirement(
                    "r", HrFrozenConfig.Dimension.SKILL, BigDecimal.ONE, true, true)),
            80,
            65,
            50,
            BigDecimal.valueOf(80),
            BigDecimal.valueOf(90));
    var draft =
        new Draft(
            "p",
            "合成岗位",
            "TECHNOLOGY",
            "d",
            "P6",
            "",
            "PREVIEW",
            scoring,
            List.of(),
            List.of(
                new SemanticCriterion(
                    "r", "Java", "SKILL", "使用Java", "强", "满足", "部分", "未满足", true)),
            1);
    return new ConfigVersion("cfg", "p", "v1.0", "ctx-1", draft, "hash", "1", Instant.now());
  }

  void setup() {
    when(positions.withCurrentContext(any(), any(), any()))
        .thenAnswer(invocation -> invocation.getArgument(2));
    when(positions.get(actor, "p")).thenReturn(position());
    when(positions.config(actor, "p", "v1.0")).thenReturn(config());
    when(candidates.facts(actor, "c")).thenReturn(facts());
    when(candidates.decode(any())).thenReturn(facts());
    when(candidates.snapshot(actor, "c"))
        .thenReturn(new Snapshot("s", "t", "c", "r", 1, "sealed", "1", Instant.now().toString()));
  }

  @Test
  void modelFailureIsFailedRunAndNeverNegativeCandidateResult() {
    setup();
    Run run = service.prepare(actor, new MatchRequest("c", "p", 1), "idem-12345");
    when(repository.run("t", run.id())).thenReturn(run);
    when(repository.start("t", run.id())).thenReturn(true);
    Run running =
        new Run(
            run.id(),
            run.tenantId(),
            run.candidateId(),
            run.positionId(),
            "RUNNING",
            null,
            null,
            run.createdAt(),
            run.inputJson(),
            run.deadlineAt(),
            run.idempotencyKey(),
            run.requestHash(),
            run.scopeRef());
    when(repository.run("t", run.id())).thenReturn(running);
    when(gateway.execute(eq(actor), eq(6103L), eq(run.scopeRef()), any()))
        .thenThrow(new HrBusinessException("HR_CONFIG_MODEL_MISSING", "模型不可用", 503));
    assertThrows(
        HrBusinessException.class,
        () -> service.execute(actor, new MatchRequest("c", "p", 1), run.id()));
    verify(repository).finishRun("t", run.id(), "FAILED", null, "HR_CONFIG_MODEL_MISSING");
    verify(repository, never()).completeRun(anyString(), anyString(), any(), any());
  }

  @Test
  void duplicateSubmitReusesRunAndNeverInsertsAgain() {
    setup();
    Run first = service.prepare(actor, new MatchRequest("c", "p", 1), "idem-12345");
    when(repository.findIdempotency("t", "idem-12345")).thenReturn(first);
    assertEquals(
        first.id(), service.prepare(actor, new MatchRequest("c", "p", 1), "idem-12345").id());
    verify(repository, times(1)).insertRun(any());
  }

  @Test
  void changedFactsCannotStartTask() {
    setup();
    assertThrows(
        HrBusinessException.class,
        () -> service.prepare(actor, new MatchRequest("c", "p", 0), "idem-12345"));
    verify(repository, never()).insertRun(any());
  }
}
