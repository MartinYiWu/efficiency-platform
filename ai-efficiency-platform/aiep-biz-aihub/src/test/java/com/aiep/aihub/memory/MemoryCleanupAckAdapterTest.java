package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.application.memory.MemoryDeletionService.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.AiInvokeFacade;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryCleanupAckAdapterTest {
 @Test void unknownEmptyMappingDoesNotInventNoCheckpointProof(){
  var packets=mock(MemoryPacketMapper.class);var ai=mock(AiInvokeFacade.class);var proof=mock(MemoryLocalCleanupProof.class);
  var request=new RevocationRequest("tenant","event","job","item",1,2,1,List.of());
  when(proof.verify(request)).thenReturn(new MemoryLocalCleanupProof.Proof(false,false,false));
  assertTrue(new MemoryCleanupAckAdapter(packets,ai,proof).acknowledge(request).receipts().isEmpty());verifyNoInteractions(ai);
 }
 @Test void onlyLockedCompleteNeverExecutedClosureCanAcknowledgeNoBackend(){
  var packets=mock(MemoryPacketMapper.class);var ai=mock(AiInvokeFacade.class);var proof=mock(MemoryLocalCleanupProof.class);
  var request=new RevocationRequest("tenant","event","job","item",1,2,1,List.of());
  when(proof.verify(request)).thenReturn(new MemoryLocalCleanupProof.Proof(true,true,true));
  var ack=new MemoryCleanupAckAdapter(packets,ai,proof).acknowledge(request);
  assertEquals(Set.of(CleanupTarget.HISTORY,CleanupTarget.DERIVED,CleanupTarget.THREADS,CleanupTarget.INDEX,CleanupTarget.AGENT_STOP),ack.receipts().keySet());
  assertFalse(ack.receipts().containsKey(CleanupTarget.VERSION_PAYLOAD));verifyNoInteractions(ai);
 }
 @Test void legacyPolicyNeverReceivesIndexNotApplicable(){
  var packets=mock(MemoryPacketMapper.class);var ai=mock(AiInvokeFacade.class);var proof=mock(MemoryLocalCleanupProof.class);
  var request=new RevocationRequest("tenant","event","job","item",1,2,1,List.of());
  when(proof.verify(request)).thenReturn(new MemoryLocalCleanupProof.Proof(true,true,false));
  assertFalse(new MemoryCleanupAckAdapter(packets,ai,proof).acknowledge(request).receipts().containsKey(CleanupTarget.INDEX));
 }
}
