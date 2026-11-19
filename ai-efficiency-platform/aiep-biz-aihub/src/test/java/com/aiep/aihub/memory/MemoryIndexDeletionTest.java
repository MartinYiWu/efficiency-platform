package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.application.memory.MemoryCleanupAckAdapter.*;
import com.aiep.aihub.application.memory.MemoryDeletionService.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemorySemanticTransport.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.support.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryIndexDeletionTest {
    @Test void provisionedUnknownDeleteNeverFallsBackToUnprovisionedIndexAck(){
        var packets=mock(MemoryPacketMapper.class);var ai=mock(AiInvokeFacade.class);var local=mock(MemoryLocalCleanupProof.class);var index=mock(IndexDeletionPort.class);
        var request=new RevocationRequest("t","event","job","item",1,1,1,List.of());
        when(local.verify(request)).thenReturn(new MemoryLocalCleanupProof.Proof(true,true,true));
        when(index.acknowledgeIndex(request)).thenReturn(new IndexDeletionProof(false,null));
        var acknowledgement=new MemoryCleanupAckAdapter(packets,ai,local,index).acknowledge(request);
        assertFalse(acknowledgement.receipts().containsKey(CleanupTarget.INDEX));verify(index).acknowledgeIndex(request);verifyNoInteractions(ai);
    }
    @Test void exactCpuDeleteReceiptIsRequiredAndNoPaidUpsertRuns(){
        var mapper=mock(MemoryIndexMapper.class);var ai=mock(AiInvokeFacade.class);
        var row=new MemoryIndexMapper.Job(b("t"),b("index-job"),b("u"),"operations",b("item"),b("version"),3,1,"a".repeat(64),"model",8,"policy",b("execution"),b("task"),"{}",Instant.now().plusSeconds(30),"DELETE_PENDING",b("request"),"b".repeat(64),2,null);
        when(mapper.indexTablePresent()).thenReturn(1);when(mapper.itemJobs(any(),any())).thenReturn(List.of(row));when(mapper.find(any(),any())).thenReturn(row);
        when(ai.deleteMemoryIndex(eq("t"),any())).thenAnswer(call->{Delete request=call.getArgument(1);return new Receipt(request.eventId(),request.scope().key(),"different-item",null,request.generation(),request.deletionEpoch(),"DELETED");});
        var manager=new AbstractPlatformTransactionManager(){protected Object doGetTransaction(){return new Object();}protected void doBegin(Object t,org.springframework.transaction.TransactionDefinition d){}protected void doCommit(DefaultTransactionStatus s){}protected void doRollback(DefaultTransactionStatus s){}};
        var service=new MemoryIndexDeletionService(mapper,ai,manager);var request=new RevocationRequest("t","event","delete-job","item",2,2,2,List.of());
        assertThrows(IllegalArgumentException.class,()->service.acknowledgeIndex(request));
        verify(ai).deleteMemoryIndex(eq("t"),any());verify(ai,never()).upsertMemoryIndex(any(),any());verify(mapper,never()).confirmDeleted(any(),any(),anyLong(),any());
    }
    static byte[] b(String value){return MemoryMapper.identity(value);}
}
