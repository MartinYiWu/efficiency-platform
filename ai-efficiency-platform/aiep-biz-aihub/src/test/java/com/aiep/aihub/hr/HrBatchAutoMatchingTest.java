package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.api.hr.HrPositionContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrBatchMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrBatchAutoMatchingTest {
  @Test
  void candidate_is_bound_before_matching_and_completed_only_after_synchronous_result() {
    var fixture = new Fixture();
    fixture.service.process(fixture.actor, "batch");
    var order = inOrder(fixture.mapper, fixture.matching);
    order
        .verify(fixture.mapper)
        .itemState("t", "item", "RUNNING", "RUNNING", "STRUCTURED", "candidate", null, 70);
    order
        .verify(fixture.matching)
        .prepareBound(
            eq(fixture.actor), any(), eq("batch-item-123456789012"), eq("hr-import-item"));
    order.verify(fixture.matching).execute(eq(fixture.actor), any(), eq("run"));
    order
        .verify(fixture.mapper)
        .itemState("t", "item", "RUNNING", "COMPLETED", "STRUCTURED", "candidate", null, 100);
    verifyNoInteractions(fixture.executor);
  }

  @Test
  void matching_failure_preserves_candidate_and_never_reports_completed() {
    var fixture = new Fixture();
    when(fixture.matching.execute(any(), any(), any()))
        .thenThrow(new HrBusinessException("PAID_BUDGET_EXHAUSTED", "预算不足", 409));
    fixture.service.process(fixture.actor, "batch");
    verify(fixture.mapper)
        .itemState(
            "t", "item", "RUNNING", "FAILED", "FAILED", "candidate", "PAID_BUDGET_EXHAUSTED", 100);
    verify(fixture.mapper, never())
        .itemState(any(), any(), any(), eq("COMPLETED"), any(), any(), any(), anyInt());
    verifyNoInteractions(fixture.executor);
  }

  private static class Fixture {
    final HrBatchMapper mapper = mock(HrBatchMapper.class);
    final HrPositionService positions = mock(HrPositionService.class);
    final HrCandidateService candidates = mock(HrCandidateService.class);
    final HrMatchingService matching = mock(HrMatchingService.class);
    final HrMatchingRunExecutor executor = mock(HrMatchingRunExecutor.class);
    final HrSensitiveJsonCodec codec = mock(HrSensitiveJsonCodec.class);
    final HrActor actor =
        new HrActor("t", "u", Set.of("d"), Set.of("hr:candidate:read", "hr:candidate:upload"));
    final HrBatchService service =
        new HrBatchService(
            mapper,
            positions,
            candidates,
            matching,
            executor,
            codec,
            new com.fasterxml.jackson.databind.ObjectMapper());

    Fixture() {
      var batch =
          new HrBatchMapper.BatchRow(
              "batch",
              "t",
              "d",
              "u",
              "p",
              "MATCH",
              "policy",
              10,
              "RUNNING",
              1,
              Instant.now(),
              "idem-key",
              "hash");
      var item =
          new HrBatchMapper.ItemRow(
              "item",
              "t",
              "batch",
              "resume.txt",
              "cipher",
              "123456789012abcdef",
              "RUNNING",
              "EXTRACTING",
              null,
              null,
              10);
      when(mapper.batch("t", "batch")).thenReturn(batch);
      when(mapper.items("t", "batch")).thenReturn(List.of(item));
      when(mapper.item("t", "item")).thenReturn(item);
      when(mapper.itemState(any(), any(), any(), any(), any(), any(), any(), anyInt()))
          .thenReturn(1);
      when(codec.open("cipher")).thenReturn("content");
      var facts =
          new Facts(
              "candidate",
              "r",
              "resume.txt",
              1,
              100,
              "CONFIRMED",
              new Profile("合成", "本科", 36, ""),
              List.of(),
              List.of(),
              List.of(),
              0,
              0,
              1);
      when(candidates.importResume(eq(actor), any(), eq("hr-import-item"), any()))
          .thenReturn(facts);
      var p =
          new Position(
              "p",
              "t",
              "岗位",
              "TECHNOLOGY",
              "d",
              "P3",
              "code",
              "ACTIVE",
              "v1",
              "ctx",
              "u",
              Instant.now(),
              1);
      when(positions.get(actor, "p")).thenReturn(p);
      var draft =
          new Draft(
              "p", "岗位", "TECHNOLOGY", "d", "P3", "", "PREVIEW", null, List.of(), List.of(), 1);
      when(positions.config(actor, "p", "v1"))
          .thenReturn(
              new ConfigVersion("config", "p", "v1", "ctx", draft, "hash", "u", Instant.now()));
      when(matching.prepareBound(eq(actor), any(), any(), any()))
          .thenAnswer(
              i -> {
                verify(mapper)
                    .itemState(
                        "t", "item", "RUNNING", "RUNNING", "STRUCTURED", "candidate", null, 70);
                return new Run(
                    "run",
                    "t",
                    "candidate",
                    "p",
                    "PENDING",
                    null,
                    null,
                    Instant.now(),
                    "cipher",
                    Instant.now().plusSeconds(600),
                    "key",
                    "hash",
                    "hr-import-item");
              });
    }
  }
}
