package com.aiep.aihub.application.memory;

import com.aiep.aihub.application.memory.MemoryDeletionService.*;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
@ConditionalOnProperty(name="aiep.memory.deletion-worker-enabled",havingValue="true",matchIfMissing=false)
public class MemoryCleanupAckAdapter implements RevocationAckPort {
 private final MemoryPacketMapper packets;
 private final AiInvokeFacade ai;
 private final MemoryLocalCleanupProof localProof;
 private static final ObjectMapper JSON=new ObjectMapper();
 public MemoryCleanupAckAdapter(MemoryPacketMapper packets,AiInvokeFacade ai,MemoryLocalCleanupProof localProof){this.packets=packets;this.ai=ai;this.localProof=localProof;}
 public Acknowledgement acknowledge(RevocationRequest request){
  if(TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("MEMORY_CLEANUP_OUTSIDE_TRANSACTION_REQUIRED");
  var local=localProof.verify(request);
  var refs=new EnumMap<CleanupTarget,String>(CleanupTarget.class);
  if(local.projectionsRevoked())refs.put(CleanupTarget.HISTORY,opaque("HISTORY",request.tenantId(),request.eventId()));
  if(local.indexUnprovisioned())refs.put(CleanupTarget.INDEX,opaque("INDEX_NOT_PROVISIONED",request.tenantId(),request.eventId()));
  if(local.projectionsRevoked()&&local.noExecutions()){
   for(var target:List.of(CleanupTarget.DERIVED,CleanupTarget.AGENT_STOP,CleanupTarget.THREADS))refs.put(target,opaque("NO_EXECUTION_"+target.name(),request.tenantId(),request.eventId()));
   return new Acknowledgement(request.eventId(),request.deletionEpoch(),refs);
  }
  var executions=new TreeMap<String,List<MemoryContextPacket.Dependency>>();
  for(var dependency:request.dependencies()){
   byte[] execution=dependency.executionId();
   if("EXECUTION".equals(dependency.targetType())){
    if(execution==null||!Arrays.equals(execution,dependency.targetId()))return Acknowledgement.pending(request.eventId(),request.deletionEpoch());
   }
   if(execution!=null&&execution.length>0)executions.computeIfAbsent(text(execution),key->new ArrayList<>()).add(new MemoryContextPacket.Dependency(dependency.sourceType(),text(dependency.sourceId()),text(dependency.sourceVersion()),dependency.grantEpoch(),dependency.sourceEpoch(),dependency.deletionEpoch()));
  }
  // 没有执行映射不是无checkpoint证明；保留五目标待确认。
  if(executions.isEmpty())return new Acknowledgement(request.eventId(),request.deletionEpoch(),refs);
  var confirmed=EnumSet.of(CleanupTarget.AGENT_STOP,CleanupTarget.THREADS,CleanupTarget.DERIVED);
  if(!local.projectionsRevoked())confirmed.remove(CleanupTarget.DERIVED);
  for(var entry:executions.entrySet()){
   try{
    var packet=packets.findPacket(request.tenantId().getBytes(StandardCharsets.UTF_8),entry.getKey().getBytes(StandardCharsets.UTF_8));
    if(packet==null||!entry.getKey().equals(text(packet.executionId())))return Acknowledgement.pending(request.eventId(),request.deletionEpoch());
    var original=JSON.readValue(packet.dependenciesJson(),new TypeReference<List<MemoryContextPacket.Dependency>>(){});
    var affected=entry.getValue().stream().distinct().toList();
    if(!original.containsAll(affected))return Acknowledgement.pending(request.eventId(),request.deletionEpoch());
    String event=opaque("event",request.tenantId(),request.eventId(),entry.getKey());
    var command=new MemoryCleanupRequest(event,packet.executionRevision(),Math.max(request.grantEpoch(),packet.grantEpoch()+1),Math.max(request.sourceEpoch(),packet.sourceEpoch()+1),Math.max(request.deletionEpoch(),packet.deletionEpoch()+1),affected);
    var receipt=ai.cleanupMemoryExecution(request.tenantId(),entry.getKey(),command);
    if(receipt==null||!entry.getKey().equals(receipt.executionId())||!event.equals(receipt.eventId())||command.deletionEpoch()!=receipt.deletionEpoch())return Acknowledgement.pending(request.eventId(),request.deletionEpoch());
    for(var target:List.copyOf(confirmed)){
     String ref=receipt.receipts().get(target==CleanupTarget.DERIVED?"SNAPSHOT":target.name());
     if(ref==null||!ref.matches("[A-Za-z0-9:_-]{16,160}"))confirmed.remove(target);
    }
   }catch(Exception error){return Acknowledgement.pending(request.eventId(),request.deletionEpoch());}
  }
  for(var target:confirmed)refs.put(target,opaque(target.name(),request.tenantId(),request.eventId(),Long.toString(request.deletionEpoch())));
  return new Acknowledgement(request.eventId(),request.deletionEpoch(),refs);
 }
 private static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
 private static String opaque(String target,String... values){try{var digest=MessageDigest.getInstance("SHA-256");for(var value:values){digest.update(value.getBytes(StandardCharsets.UTF_8));digest.update((byte)0);}return "memory-"+target+":"+HexFormat.of().formatHex(digest.digest());}catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}}
}
