package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingHardAtomsTest {
  Matching execute(String mode) throws Exception {
    var f = new HrMatchingLifecycleTest();
    f.setup();
    ConfigVersion original = f.config();
    Draft d = original.snapshot();
    List<SemanticCriterion> criteria = new ArrayList<>(d.criteria());
    criteria.add(
        new SemanticCriterion(
            "h", "技能组合", "SKILL", "实际使用技能", "有多项成果", "实际使用", "部分使用", "明确未使用", true));
    Draft draft =
        new Draft(
            d.positionId(),
            d.name(),
            d.family(),
            d.departmentId(),
            d.level(),
            d.jdText(),
            d.lastStep(),
            d.scoring(),
            List.of(
                new HardRule(
                    "h",
                    "REQUIRED_SKILL",
                    "必备技能",
                    "Java/Python",
                    null,
                    null,
                    null,
                    false,
                    List.of("Java", "Python"),
                    mode)),
            criteria,
            d.version());
    ConfigVersion config =
        new ConfigVersion("cfg", "p", "v1.0", "ctx-1", draft, "hash", "1", Instant.now());
    when(f.positions.config(f.actor, "p", "v1.0")).thenReturn(config);
    Run run = f.service.prepare(f.actor, new MatchRequest("c", "p", 1), "hard-12345");
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
    when(f.repository.run("t", run.id())).thenReturn(running);
    when(f.repository.start("t", run.id())).thenReturn(true);
    when(f.repository.completeRun(anyString(), anyString(), any(), any())).thenReturn(true);
    when(f.gateway.execute(eq(f.actor), eq(6103L), eq(run.scopeRef()), any()))
        .thenAnswer(
            invocation -> {
              var input =
                  (com.fasterxml.jackson.databind.node.ObjectNode) invocation.getArgument(3);
              assertEquals(3, input.get("requirements").size());
              var data = f.json.createObjectNode();
              var assessments = data.putArray("assessments");
              for (var req : input.get("requirements")) {
                boolean missing = req.get("criterion").asText().contains("原子标准值：Python");
                var a =
                    assessments
                        .addObject()
                        .put("requirement_id", req.get("requirement_id").asText())
                        .put("status", missing ? "UNKNOWN" : "MATCH")
                        .put("reason", missing ? "未提及Python" : "有Java工作证据");
                var evidence = a.putArray("evidence");
                if (!missing)
                  evidence
                      .addObject()
                      .put("block_id", "b")
                      .put("start", 0)
                      .put("end", 4)
                      .put("quote", "Java");
              }
              return data;
            });
    when(f.gateway.execute(eq(f.actor), eq(6104L), eq(run.scopeRef()), any()))
        .thenReturn(f.json.readTree("{\"highlights\":[],\"gaps\":[]}"));
    return f.service.execute(f.actor, new MatchRequest("c", "p", 1), run.id());
  }

  @Test
  void allKeepsUnknownAtomUnverified() throws Exception {
    Matching result = execute("ALL");
    assertEquals("UNKNOWN", result.hardConditions().getFirst().status());
    assertEquals("REVIEW_REQUIRED", result.businessStatus());
    assertNull(result.totalScore());
  }

  @Test
  void anyPassesWhenOneVerifiedAtomPasses() throws Exception {
    Matching result = execute("ANY");
    assertEquals("PASS", result.hardConditions().getFirst().status());
    assertEquals("SCORED", result.businessStatus());
    assertEquals("COMPLETE", result.explanation().status());
  }
}
