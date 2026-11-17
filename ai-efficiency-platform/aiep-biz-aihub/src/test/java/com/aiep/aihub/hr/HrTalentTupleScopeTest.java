package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.*;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrTalentTupleScopeTest {
  @Test
  void each_department_query_uses_only_its_own_permission_object_tuple() {
    var mapper = mock(HrTalentMapper.class);
    when(mapper.visible(any(), any(), any(), any())).thenReturn(List.of());
    var service =
        new HrTalentSearchService(
            mapper,
            new ObjectMapper(),
            mock(HrSensitiveJsonCodec.class),
            mock(HrSourceAuthorization.class),
            mock(HrPositionService.class),
            mock(HrSettingsRepository.class));
    var actor =
        new HrActor(
            "t",
            "u",
            Set.of("a", "b"),
            Set.of("hr:candidate:read", "hr:candidate:delete"),
            Set.of("*"),
            Set.of("c1", "c2"),
            true,
            List.of(
                new HrActor.GrantScope("hr:candidate:read", "a", null, "c1"),
                new HrActor.GrantScope("hr:candidate:delete", "b", null, "c2")));
    service.visibleCandidates(actor, "hr:candidate:read", Instant.now());
    verify(mapper).visible(eq("t"), eq(Set.of("a")), eq(Set.of("c1")), any());
    verify(mapper, never()).visible(eq("t"), eq(Set.of("b")), any(), any());
  }

  @Test
  void read_permission_in_other_department_does_not_allow_contact() {
    var mapper = mock(HrTalentMapper.class);
    var c =
        new Candidate(
            "c", "t", "b", "s", 1, "p", Instant.now(), Instant.now().plusSeconds(3600), "ACTIVE");
    when(mapper.candidate("t", "c")).thenReturn(c);
    var service =
        new HrTalentSearchService(
            mapper,
            new ObjectMapper(),
            mock(HrSensitiveJsonCodec.class),
            mock(HrSourceAuthorization.class),
            mock(HrPositionService.class),
            mock(HrSettingsRepository.class));
    var actor =
        new HrActor(
            "t",
            "u",
            Set.of("a", "b"),
            Set.of("hr:candidate:read", "hr:candidate:contact"),
            Set.of("*"),
            Set.of("*"),
            true,
            List.of(
                new HrActor.GrantScope("hr:candidate:contact", "a", null, "*"),
                new HrActor.GrantScope("hr:candidate:read", "b", null, "*")));
    assertThrows(
        HrBusinessException.class, () -> service.authorized(actor, "c", "hr:candidate:contact"));
  }
}
