package com.aiep.aihub.application.memory;

import com.aiep.aihub.repository.memory.MemoryForgetMapper;
import com.aiep.aihub.repository.memory.MemoryLifecycleMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 源锁下复核原完整闭包；历史投影依赖失效与展示档案保留是不同事实。 */
@Service
public class MemoryLocalCleanupProof {
 private final MemoryForgetMapper sources;
 private final MemoryLifecycleMapper lifecycle;
 private final TransactionTemplate transaction;
 private static final ObjectMapper JSON=new ObjectMapper();
 public MemoryLocalCleanupProof(MemoryForgetMapper sources,MemoryLifecycleMapper lifecycle,PlatformTransactionManager manager){this.sources=sources;this.lifecycle=lifecycle;transaction=new TransactionTemplate(manager);}
 public record Proof(boolean projectionsRevoked,boolean noExecutions,boolean indexUnprovisioned){}
 public Proof verify(MemoryDeletionService.RevocationRequest request){
  return transaction.execute(status->{
   if(request.dependencies().isEmpty())return new Proof(false,false,false);
   byte[] tenant=request.tenantId().getBytes(StandardCharsets.UTF_8);
   var sourceIds=new TreeMap<String,byte[]>();
   for(var dep:request.dependencies())sourceIds.put(HexFormat.of().formatHex(dep.sourceId()),dep.sourceId());
   for(var id:sourceIds.values()){
    var source=sources.lockSource(tenant,id);
    if(source==null||lifecycle.sourceTombstone(tenant,id,source.deletionEpoch())!=1)return new Proof(false,false,false);
    for(var dep:request.dependencies())if(Arrays.equals(id,dep.sourceId())){
     if(!Arrays.equals(source.sourceVersion(),dep.sourceVersion())||source.grantEpoch()<=dep.grantEpoch()||source.sourceEpoch()<=dep.sourceEpoch()||source.deletionEpoch()<=dep.deletionEpoch())return new Proof(false,false,false);
    }
   }
   var current=sources.listSourcesDependenciesCurrent(tenant,List.copyOf(sourceIds.values()));
   try{
    var expected=new HashSet<String>();for(var dep:request.dependencies())expected.add(JSON.writeValueAsString(dep));
    var actual=new HashSet<String>();for(var dep:current)actual.add(JSON.writeValueAsString(dep));
    if(!expected.equals(actual))return new Proof(false,false,false);
    boolean noExecutions=true,index=true;record Target(byte[] item,byte[] version){}var items=new TreeMap<String,Target>();
    byte[] own=request.itemId().getBytes(StandardCharsets.UTF_8);items.put(request.itemId(),new Target(own,null));
    for(var dep:current){
     if(!Set.of("MEMORY_VERSION","MESSAGE","EXECUTION").contains(dep.targetType()))return new Proof(false,false,false);
     if("EXECUTION".equals(dep.targetType())||dep.executionId()!=null&&dep.executionId().length>0)noExecutions=false;
     if("MEMORY_VERSION".equals(dep.targetType())&&!Arrays.equals(own,dep.targetId()))items.put(HexFormat.of().formatHex(dep.targetId())+":"+HexFormat.of().formatHex(dep.targetVersion()),new Target(dep.targetId(),dep.targetVersion()));
     if(dep.rootThreadRef()!=null||dep.childThreadRef()!=null||dep.checkpointNamespace()!=null)noExecutions=false;
    }
    for(var item:items.values()){
     var versions=lifecycle.versionProofs(tenant,item.item(),item.version());
     if(versions.isEmpty())return new Proof(false,false,false);
     for(var version:versions){
      if(!Set.of("REVOKED","DELETED").contains(version.status()))return new Proof(false,false,false);
      try{MemoryPolicyService.requireUnprovisionedIndex(JSON.readTree(version.policyJson()));}
      catch(Exception unsupported){index=false;}
     }
    }
    return new Proof(true,noExecutions,index);
   }catch(java.io.IOException invalid){return new Proof(false,false,false);}
  });
 }
}
