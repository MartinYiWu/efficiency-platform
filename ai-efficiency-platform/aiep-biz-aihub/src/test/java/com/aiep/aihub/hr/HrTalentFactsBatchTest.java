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

class HrTalentFactsBatchTest {
  @Test
  void authorized_sources_load_all_snapshots_once_and_reuse_snapshot_timestamps() throws Exception {
    var mapper = mock(HrTalentMapper.class);
    var codec = mock(HrSensitiveJsonCodec.class);
    var json = new ObjectMapper();
    var service =
        new HrTalentSearchService(
            mapper,
            json,
            codec,
            mock(HrSourceAuthorization.class),
            mock(HrPositionService.class),
            mock(HrSettingsRepository.class));
    var actor = new HrActor("t", "u", Set.of("d"), Set.of("hr:candidate:read"));
    Instant acquired = Instant.parse("2026-01-01T00:00:00Z"),
        updated = Instant.parse("2026-10-01T00:00:00Z");
    List<Candidate> candidates =
        List.of(
            new Candidate(
                "a", "t", "d", "s1", 1, "p", acquired, Instant.now().plusSeconds(3600), "ACTIVE"),
            new Candidate(
                "b", "t", "d", "s2", 1, "p", acquired, Instant.now().plusSeconds(3600), "ACTIVE"));
    when(mapper.snapshotsByIds(eq("t"), eq(Set.of("s1", "s2"))))
        .thenReturn(
            List.of(
                new Snapshot("s1", "t", "a", "r1", 1, "cipher1", "u", updated.toString()),
                new Snapshot("s2", "t", "b", "r2", 1, "cipher2", "u", updated.toString())));
    for (int i = 0; i < 2; i++) {
      String id = i == 0 ? "a" : "b";
      var facts =
          new Facts(
              id,
              "r" + (i + 1),
              "resume",
              1,
              100,
              "READY",
              new Profile("合成", "本科", 12, ""),
              List.of(),
              List.of(),
              List.of(),
              0,
              0,
              1);
      when(codec.open("cipher" + (i + 1))).thenReturn(json.writeValueAsString(facts));
    }
    var batch = service.factsBatch(actor, candidates);
    assertEquals(2, batch.size());
    assertEquals(updated, batch.get("a").updatedAt());
    assertEquals("b", batch.get("b").facts().candidateId());
    verify(mapper, times(1)).snapshotsByIds("t", Set.of("s1", "s2"));
    verify(mapper, never()).snapshot(any(), any());
    var denied =
        new Candidate(
            "private",
            "t",
            "other",
            "secret",
            1,
            "p",
            acquired,
            Instant.now().plusSeconds(3600),
            "ACTIVE");
    assertThrows(HrBusinessException.class, () -> service.factsBatch(actor, List.of(denied)));
    verify(mapper, times(1)).snapshotsByIds(any(), any());
  }
}
