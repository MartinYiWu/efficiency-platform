package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.api.hr.*;
import com.aiep.aihub.api.hr.HrCandidateContracts.Candidate;
import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;

class HrMatchingPurposeTest {
  @Test
  void talent_pool_allows_cross_position_but_recruitment_only_original_batch_target() {
    var mapper = mock(HrExecutionMapper.class);
    var batches = mock(HrBatchMapper.class);
    var source =
        new HrSourceAuthorization(
            mapper, mock(HrSensitiveJsonCodec.class), new ObjectMapper(), batches);
    var actor = new HrActor("t", "1", Set.of("d"), Set.of("hr:candidate:read"));
    var candidate =
        new Candidate(
            "c",
            "t",
            "d",
            "s",
            1,
            "policy",
            Instant.now(),
            Instant.now().plusSeconds(100),
            "ACTIVE");
    when(mapper.sourceByCandidate("t", "c"))
        .thenReturn(
            new HrExecutionMapper.SourceRow(
                "t",
                "c",
                "policy",
                "TALENT_POOL,INTERVIEW",
                "sealed",
                "sealed",
                null,
                Instant.now(),
                "WAITING"));
    assertDoesNotThrow(() -> source.requireMatching(actor, candidate, "new-position"));
    when(mapper.sourceByCandidate("t", "c"))
        .thenReturn(
            new HrExecutionMapper.SourceRow(
                "t",
                "c",
                "policy",
                "RECRUITMENT,INTERVIEW",
                "sealed",
                "sealed",
                null,
                Instant.now(),
                "WAITING"));
    when(batches.candidateBatch("t", "c"))
        .thenReturn(
            new HrBatchMapper.BatchRow(
                "batch",
                "t",
                "d",
                "1",
                "original",
                "MATCH",
                "policy",
                10,
                "COMPLETED",
                1,
                Instant.now(),
                "key",
                "hash"));
    assertDoesNotThrow(() -> source.requireMatching(actor, candidate, "original"));
    assertThrows(
        HrBusinessException.class, () -> source.requireMatching(actor, candidate, "new-position"));
  }
}
