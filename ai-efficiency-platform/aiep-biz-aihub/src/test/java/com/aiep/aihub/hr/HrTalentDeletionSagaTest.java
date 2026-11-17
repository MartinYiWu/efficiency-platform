package com.aiep.aihub.hr;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.aiep.aihub.application.hr.*;
import com.aiep.aihub.repository.hr.HrTalentMapper;
import java.time.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;

class HrTalentDeletionSagaTest {
  @Test
  void failed_index_stays_invisible_and_retries_without_advancing() {
    var mapper = mock(HrTalentMapper.class);
    var port = mock(HrDeletionEffectsPort.class);
    ObjectProvider<HrDeletionEffectsPort> provider = mock(ObjectProvider.class);
    when(provider.getIfAvailable()).thenReturn(port);
    doThrow(new IllegalStateException()).when(port).deleteIndex(any(), any(), any());
    var service =
        new HrDeletionService(
            mapper, mock(HrTalentSearchService.class), mock(HrAuditService.class), provider);
    var job =
        new HrTalentMapper.JobRow(
            "j", "t", "c", "d", "PENDING", "INDEX", 0, Instant.now(), Instant.now(), null);
    service.process(job);
    verify(mapper).failJob(eq("t"), eq("j"), eq(1), any(), eq("HR_DELETION_STEP_FAILED"));
    verify(mapper, never()).advanceJob(any(), any(), any(), any());
    verify(mapper, never()).completeCandidate(any(), any());
  }

  @Test
  void successful_steps_have_separate_durable_receipts() {
    var mapper = mock(HrTalentMapper.class);
    var port = mock(HrDeletionEffectsPort.class);
    ObjectProvider<HrDeletionEffectsPort> provider = mock(ObjectProvider.class);
    when(provider.getIfAvailable()).thenReturn(port);
    var service =
        new HrDeletionService(
            mapper, mock(HrTalentSearchService.class), mock(HrAuditService.class), provider);
    service.process(
        new HrTalentMapper.JobRow(
            "j", "t", "c", "d", "PENDING", "INDEX", 0, Instant.now(), Instant.now(), null));
    verify(port).deleteIndex("t", "c", "j:index");
    verify(mapper).advanceJob("t", "j", "INDEX", "BUSINESS");
    service.process(
        new HrTalentMapper.JobRow(
            "j", "t", "c", "d", "PENDING", "FILES", 0, Instant.now(), Instant.now(), null));
    verify(port).releaseFilesAndCaches("t", "c", "j:files");
    verify(mapper).completeCandidate("t", "c");
    verify(mapper).completeJob("t", "j");
  }
}
