package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryForgetMapper;
import com.aiep.aihub.repository.memory.MemoryForgetMapper.*;
import java.time.Instant;
import java.util.*;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static com.aiep.aihub.application.memory.MemoryForgetService.*;

/** CPU补偿与真实清理确认分离；没有生产port或完整确认时永不把未知thread当作不存在。 */
@Service
public class MemoryDeletionService {
 private final MemoryMapper memories;private final MemoryForgetMapper mapper;private final TransactionTemplate transactions;private final ObjectProvider<RevocationAckPort> ports;
 public MemoryDeletionService(MemoryMapper memories,MemoryForgetMapper mapper,PlatformTransactionManager manager,ObjectProvider<RevocationAckPort> ports){this.memories=memories;this.mapper=mapper;this.transactions=new TransactionTemplate(manager);this.ports=ports;}
 public void compensate(String tenantId,String jobId){
  var request=transactions.execute(tx->{
   var read=mapper.readJob(b(tenantId),b(jobId));if(read==null)throw new MemoryException("MEMORY_NOT_FOUND");
   var item=memories.findItemForUpdate(read.tenantId(),read.itemId());var job=mapper.findJob(read.tenantId(),read.id());
   if("SUCCEEDED".equals(job.status()))return null;
   if(item==null||!"DELETE_PENDING".equals(item.lifecycle())||item.deletionEpoch()!=job.deletionEpoch())throw new MemoryException("MEMORY_REVISION_CONFLICT");
   if(job.attempts()>=8||job.deadline()==null||!job.deadline().isAfter(Instant.now()))return null;
   var state=decode(job.receipts());
   one(mapper.updateJob(new JobPO(job.tenantId(),job.id(),job.itemId(),job.deletionEpoch(),job.requestId(),job.requestedBy(),"RUNNING",job.requiredTargets(),job.completedTargets(),job.revision(),job.attempts()+1,job.deadline(),job.receipts()),job.revision()));
   return new RevocationRequest(tenantId,state.eventId(),jobId,text(job.itemId()),item.grantEpoch(),item.sourceEpoch(),item.deletionEpoch(),List.copyOf(state.dependencies()));
  });
  if(request==null)return;
  var port=ports.getIfAvailable();var ack=port==null?Acknowledgement.pending(request.eventId(),request.deletionEpoch()):port.acknowledge(request);
  if(ack==null||!request.eventId().equals(ack.eventId())||request.deletionEpoch()!=ack.deletionEpoch())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  transactions.executeWithoutResult(tx->{
   var item=memories.findItemForUpdate(b(tenantId),b(request.itemId()));var job=mapper.findJob(b(tenantId),b(jobId));
   if("SUCCEEDED".equals(job.status()))return;
   if(item==null||!"DELETE_PENDING".equals(item.lifecycle())||item.deletionEpoch()!=request.deletionEpoch())throw new MemoryException("MEMORY_REVISION_CONFLICT");
   var state=decode(job.receipts());var receipts=new HashMap<>(state.receipts());
   for(var entry:ack.receipts().entrySet()){
    if(entry.getKey()==CleanupTarget.VERSION_PAYLOAD)throw new MemoryException("MEMORY_REQUEST_INVALID");
    b(entry.getValue());receipts.put(entry.getKey().name(),entry.getValue());
   }
   boolean complete=receipts.keySet().containsAll(Set.of("DERIVED","HISTORY","THREADS","INDEX","AGENT_STOP"));
   int payloads=complete?mapper.countPendingVersions(job.tenantId(),job.itemId()):0;
   if(complete&&payloads<1)throw new MemoryException("MEMORY_REVISION_CONFLICT");
   if(complete)receipts.put("VERSION_PAYLOAD","LOCAL_ATOMIC_SCRUB");
   var next=new CleanupState(state.eventId(),state.requestFingerprint(),state.suppressionId(),state.suppressionRevision(),state.dependencies(),Map.copyOf(receipts));
   one(mapper.updateJob(new JobPO(job.tenantId(),job.id(),job.itemId(),job.deletionEpoch(),job.requestId(),job.requestedBy(),complete?"SUCCEEDED":"BLOCKED",job.requiredTargets(),receipts.size(),job.revision(),job.attempts(),job.deadline(),encode(next)),job.revision()));
   if(complete){
    // D10仅允许已有全目标SUCCEEDED授权的单次REVOKED→DELETED擦除；所有变化在同一commit可见。
    if(mapper.scrubVersions(job.tenantId(),job.itemId(),job.deletionEpoch())!=payloads)throw new MemoryException("MEMORY_REVISION_CONFLICT");
    one(mapper.completeItem(job.tenantId(),job.itemId(),job.deletionEpoch(),item.revision()));
    one(mapper.completeOutbox(job.tenantId(),b(state.eventId())));
   }
  });
 }
 public enum CleanupTarget {VERSION_PAYLOAD,DERIVED,HISTORY,THREADS,INDEX,AGENT_STOP}
 public interface RevocationAckPort {Acknowledgement acknowledge(RevocationRequest request);}
 public record RevocationRequest(String tenantId,String eventId,String jobId,String itemId,long grantEpoch,long sourceEpoch,long deletionEpoch,List<DependencyPO> dependencies){}
 public record Acknowledgement(String eventId,long deletionEpoch,Map<CleanupTarget,String> receipts){public Acknowledgement{receipts=Map.copyOf(receipts);}public static Acknowledgement pending(String eventId,long deletionEpoch){return new Acknowledgement(eventId,deletionEpoch,Map.of());}}
}
