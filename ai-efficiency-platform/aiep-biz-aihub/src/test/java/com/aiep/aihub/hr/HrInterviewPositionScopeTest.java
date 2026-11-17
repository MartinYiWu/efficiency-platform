package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.api.hr.HrInterviewContracts.InterviewSet;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.transaction.PlatformTransactionManager;

class HrInterviewPositionScopeTest {
  @Test
  void candidate_read_cannot_read_interview_from_another_position() throws Exception {
    var actor =
        new HrActor(
            "t",
            "1",
            Set.of("d"),
            Set.of("hr:candidate:read", "hr:interview:read", "hr:position:read"),
            Set.of("allowed"),
            Set.of("c"));
    var mapper = mock(HrTalentMapper.class);
    var talent = mock(HrTalentSearchService.class);
    var positions = mock(HrPositionService.class);
    var json = JsonMapper.builder().findAndAddModules().build();
    var codec = new HrSensitiveJsonCodec(Base64.getEncoder().encodeToString(new byte[32]));
    var payload =
        new InterviewSet(
            "s", "c", "private", 2, "READY", 30, 0, List.of(), List.of(), Instant.now());
    when(mapper.set("t", "s", null))
        .thenReturn(
            new HrTalentMapper.SetRow(
                "s",
                "t",
                "c",
                "private",
                2,
                "READY",
                codec.seal(json.writeValueAsString(payload)),
                "[\"c\"]",
                "hash",
                "1",
                Instant.now()));
    when(talent.authorized(actor, "c", "hr:candidate:read"))
        .thenReturn(new Candidate("c", "t", "d", "f", 1));
    when(positions.get(actor, "private"))
        .thenThrow(new HrBusinessException("HR_OBJECT_NOT_FOUND", "不可访问", 404));
    ObjectProvider<HrInterviewBindingPort> bindings = mock(ObjectProvider.class);
    var service =
        new HrInterviewService(
            mock(HrActorAuthority.class),
            mock(HrInterviewTemplateService.class),
            mapper,
            talent,
            positions,
            mock(HrSemanticGateway.class),
            json,
            codec,
            mock(HrAuditService.class),
            mock(PlatformTransactionManager.class),
            bindings);
    assertEquals(
        404, assertThrows(HrBusinessException.class, () -> service.get(actor, "s", null)).status());
  }
}
