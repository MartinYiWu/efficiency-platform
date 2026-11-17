package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.HrActor;
import com.aiep.aihub.application.hr.*;
import com.aiep.identity.api.IdentityFacade;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrActorAuthorityTest {
  @Test
  void authenticated_jobs_refresh_and_lose_revoked_grants() {
    var identity = mock(IdentityFacade.class);
    var actor =
        new HrActor(
            "t",
            "1",
            Set.of("d"),
            Set.of("hr:candidate:read"),
            Set.of("*"),
            Set.of("*"),
            true,
            List.of(),
            "a".repeat(64));
    when(identity.refresh("t", "1", "a".repeat(64)))
        .thenReturn(
            Optional.of(
                new IdentityFacade.Subject(
                    "t",
                    "1",
                    Set.of("d"),
                    Set.of(),
                    Set.of(),
                    Set.of(),
                    List.of(),
                    "a".repeat(64))));
    var refreshed = new HrActorAuthority(identity).refresh(actor);
    assertTrue(refreshed.authenticated());
    assertTrue(refreshed.permissions().isEmpty());
    assertThrows(HrBusinessException.class, () -> HrAccessPolicy.candidate(refreshed, "c"));
    when(identity.refresh("t", "1", "a".repeat(64))).thenReturn(Optional.empty());
    assertThrows(HrBusinessException.class, () -> new HrActorAuthority(identity).refresh(actor));
  }

  @Test
  void historical_authenticated_actor_without_exact_session_reference_fails_closed() {
    var identity = mock(IdentityFacade.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of(), Set.of(), Set.of(), true);
    assertThrows(HrBusinessException.class, () -> new HrActorAuthority(identity).refresh(actor));
    verifyNoInteractions(identity);
  }

  @Test
  void offline_development_actor_does_not_query_sessions() {
    var identity = mock(IdentityFacade.class);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of());
    assertSame(actor, new HrActorAuthority(identity).refresh(actor));
    verifyNoInteractions(identity);
  }

  @Test
  void internal_session_reference_is_not_returned_in_session_json() throws Exception {
    String reference = "a".repeat(64);
    var actor =
        new HrActor(
            "t", "1", Set.of("d"), Set.of(), Set.of(), Set.of(), true, List.of(), reference);
    String serialized = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(actor);
    assertFalse(serialized.contains(reference));
    assertFalse(serialized.contains("sessionRef"));
  }
}
