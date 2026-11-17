package com.aiep.aihub.memory;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import java.util.List;

class MemoryDeletionDispatcherTest {
 @Test void productionDispatcherExistsAndIsDisabledByDefault() throws Exception {
  var found=assertDoesNotThrow(()->Class.forName("com.aiep.aihub.application.memory.MemoryDeletionDispatcher"),"production outbox dispatcher must be present");
  var condition=found.getAnnotation(org.springframework.boot.autoconfigure.condition.ConditionalOnProperty.class);
  assertNotNull(condition);assertFalse(condition.matchIfMissing());assertEquals("true",condition.havingValue());
 }
 @Test void lostClaimNeverCallsExternalCompensation(){
  var mapper=mock(MemoryLifecycleMapper.class);var lease=mock(MemoryDeletionLease.class);var deletion=mock(MemoryDeletionService.class);
  var delivery=new MemoryLifecycleMapper.Delivery("t".getBytes(),"e".getBytes(),"j".getBytes(),1,0);
  when(mapper.due(16)).thenReturn(List.of(delivery));when(lease.run(eq(delivery),any())).thenAnswer(call->{((Runnable)call.getArgument(1)).run();return true;});
  new MemoryDeletionDispatcher(mapper,lease,deletion).dispatch();verifyNoInteractions(deletion);verify(mapper,never()).release(any(),any());
 }
 @Test void transientExternalFailureReleasesOnlyTheClaimedLeaseAndDoesNotRetryInline(){
  var mapper=mock(MemoryLifecycleMapper.class);var lease=mock(MemoryDeletionLease.class);var deletion=mock(MemoryDeletionService.class);
  var delivery=new MemoryLifecycleMapper.Delivery("t".getBytes(),"e".getBytes(),"j".getBytes(),1,0);
  when(mapper.due(16)).thenReturn(List.of(delivery));when(mapper.claim(eq(delivery),any())).thenReturn(1);
  when(lease.run(eq(delivery),any())).thenAnswer(call->{((Runnable)call.getArgument(1)).run();return true;});doThrow(new IllegalStateException()).when(deletion).compensate("t","j");
  new MemoryDeletionDispatcher(mapper,lease,deletion).dispatch();verify(deletion,times(1)).compensate("t","j");verify(mapper).release(eq(delivery),any());
 }
 @Test void ambientBusinessTransactionIsRejectedBeforeScanning(){
  var mapper=mock(MemoryLifecycleMapper.class);var lease=mock(MemoryDeletionLease.class);var deletion=mock(MemoryDeletionService.class);
  org.springframework.transaction.support.TransactionSynchronizationManager.setActualTransactionActive(true);
  try{assertThrows(IllegalStateException.class,()->new MemoryDeletionDispatcher(mapper,lease,deletion).dispatch());verifyNoInteractions(mapper,lease,deletion);}
  finally{org.springframework.transaction.support.TransactionSynchronizationManager.clear();}
 }
}
