package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.api.hr.HrInterviewContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrInterviewSecurityTest {
  @Test
  void expired_assignment_is_unreadable_without_loading_any_payload() {
    var mapper = mock(HrTalentMapper.class);
    var service =
        new HrInterviewAssignmentService(
            mapper,
            mock(HrInterviewService.class),
            mock(HrPositionService.class),
            new InterviewViewAssembler(),
            mock(HrAuditService.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of());
    when(mapper.assignment("t", "a"))
        .thenReturn(
            new HrTalentMapper.AssignmentRow(
                "a", "t", "s", 1, "u", Instant.now().minusSeconds(1), "ACTIVE", "hr"));
    assertThrows(HrBusinessException.class, () -> service.assigned(actor, "a"));
    verify(mapper, never()).set(any(), any(), any());
  }

  @Test
  void deleted_source_blocks_active_assignment() {
    var mapper = mock(HrTalentMapper.class);
    var service =
        new HrInterviewAssignmentService(
            mapper,
            mock(HrInterviewService.class),
            mock(HrPositionService.class),
            new InterviewViewAssembler(),
            mock(HrAuditService.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of());
    when(mapper.assignment("t", "a"))
        .thenReturn(
            new HrTalentMapper.AssignmentRow(
                "a", "t", "s", 1, "u", Instant.now().plusSeconds(3600), "ACTIVE", "hr"));
    when(mapper.set("t", "s", 1L))
        .thenReturn(
            new HrTalentMapper.SetRow(
                "s", "t", "c", "p", 1, "READY", "cipher", "[\"c\"]", "hash", "hr", Instant.now()));
    when(mapper.candidate("t", "c"))
        .thenReturn(
            new Candidate(
                "c",
                "t",
                "d",
                "f",
                1,
                "policy",
                Instant.now(),
                Instant.now().plusSeconds(3600),
                "DELETING"));
    assertThrows(HrBusinessException.class, () -> service.assigned(actor, "a"));
  }
}
