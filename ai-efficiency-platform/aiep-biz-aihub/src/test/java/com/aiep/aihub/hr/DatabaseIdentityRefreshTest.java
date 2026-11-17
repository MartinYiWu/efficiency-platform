package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import java.util.*;
import org.junit.jupiter.api.Test;

class DatabaseIdentityRefreshTest {
  @Test
  void expired_or_revoked_sessions_cannot_keep_background_authority() {
    var mapper = mock(IdentitySessionMapper.class);
    var identity = new DatabaseIdentityFacade(mapper);
    assertTrue(identity.refresh("t", "1").isEmpty());
    verify(mapper, never()).grants(anyString(), anyString());
    when(mapper.activeSessions(eq("t"), eq("1"), any())).thenReturn(1);
    when(mapper.grants("t", "1"))
        .thenReturn(List.of(new IdentitySessionMapper.GrantRow("d", "hr:config:read", null, null)));
    var s = identity.refresh("t", "1").orElseThrow();
    assertEquals(Set.of("hr:config:read"), s.permissions());
    assertTrue(s.candidateIds().isEmpty());
  }

  @Test
  void one_revoked_session_cannot_borrow_another_active_session() {
    var mapper = mock(IdentitySessionMapper.class);
    var identity = new DatabaseIdentityFacade(mapper);
    String ref = "a".repeat(64);
    when(mapper.activeSessions(eq("t"), eq("1"), any())).thenReturn(1);
    when(mapper.session(eq(ref), any())).thenReturn(null);
    assertTrue(identity.refresh("t", "1", ref).isEmpty());
    verify(mapper, never()).grants(anyString(), anyString());
    when(mapper.session(eq(ref), any())).thenReturn(new IdentitySessionMapper.SessionRow("t", "1"));
    when(mapper.grants("t", "1")).thenReturn(List.of());
    assertEquals(ref, identity.refresh("t", "1", ref).orElseThrow().sessionRef());
    when(mapper.session(eq(ref), any()))
        .thenReturn(new IdentitySessionMapper.SessionRow("other", "1"));
    assertTrue(identity.refresh("t", "1", ref).isEmpty());
  }

  @Test
  void authenticate_returns_only_irreversible_session_reference() throws Exception {
    var mapper = mock(IdentitySessionMapper.class);
    String credential = "synthetic-session-" + "x".repeat(43);
    String reference =
        HexFormat.of()
            .formatHex(
                java.security.MessageDigest.getInstance("SHA-256")
                    .digest(credential.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    when(mapper.session(eq(reference), any()))
        .thenReturn(new IdentitySessionMapper.SessionRow("t", "1"));
    when(mapper.grants("t", "1")).thenReturn(List.of());
    var subject = new DatabaseIdentityFacade(mapper).authenticate(credential).orElseThrow();
    assertEquals(reference, subject.sessionRef());
    assertNotEquals(credential, subject.sessionRef());
    verify(mapper, never()).activeSessions(anyString(), anyString(), any());
  }
}
