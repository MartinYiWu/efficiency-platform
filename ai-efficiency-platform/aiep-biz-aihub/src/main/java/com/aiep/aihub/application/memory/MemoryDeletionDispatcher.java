package com.aiep.aihub.application.memory;

import com.aiep.aihub.repository.memory.MemoryDeletionLease;
import com.aiep.aihub.repository.memory.MemoryLifecycleMapper;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
@ConditionalOnProperty(name="aiep.memory.deletion-worker-enabled",havingValue="true",matchIfMissing=false)
public class MemoryDeletionDispatcher {
 private final MemoryLifecycleMapper mapper;
 private final MemoryDeletionLease leases;
 private final MemoryDeletionService deletion;
 public MemoryDeletionDispatcher(MemoryLifecycleMapper mapper,MemoryDeletionLease leases,MemoryDeletionService deletion){this.mapper=mapper;this.leases=leases;this.deletion=deletion;}
 @Scheduled(fixedDelayString="${aiep.memory.deletion-scan-delay-ms:60000}")
 public void dispatch(){
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("MEMORY_CLEANUP_OUTSIDE_TRANSACTION_REQUIRED");
  for(var delivery:mapper.due(16)){
   try{leases.run(delivery,()->{
    byte[] token=UUID.randomUUID().toString().getBytes(StandardCharsets.UTF_8);
    if(mapper.claim(delivery,token)!=1)return;
    try{deletion.compensate(new String(delivery.tenantId(),StandardCharsets.UTF_8),new String(delivery.jobId(),StandardCharsets.UTF_8));}
    finally{mapper.release(delivery,token);}
   });}catch(RuntimeException error){/* 持久租约和原始deadline限制重试；不保存驱动错误或业务正文。 */}
  }
 }
}
