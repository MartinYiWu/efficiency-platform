package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.MemoryItemPO;
import com.aiep.aihub.repository.memory.MemoryForgetMapper.*;
import com.aiep.identity.api.IdentityFacade;
import java.time.Instant;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static com.aiep.aihub.application.memory.MemoryForgetService.*;

/** 源删除按完整反向依赖撤销；项目退出/撤共享尚未启用，不能伪装为全局删除。 */
@Service
public class MemorySourceInvalidationService {
 private final MemoryMapper memories;private final MemoryForgetMapper mapper;private final MemoryForgetService forget;private final TransactionTemplate transactions;
 public MemorySourceInvalidationService(MemoryMapper memories,MemoryForgetMapper mapper,MemoryForgetService forget,PlatformTransactionManager manager){this.memories=memories;this.mapper=mapper;this.forget=forget;this.transactions=new TransactionTemplate(manager);}
 public InvalidationResponse invalidateOwnedSource(IdentityFacade.Subject actor,MemoryScopeDTO scope,String sourceId,long expectedSourceEpoch){
  forget.authorize(actor,scope);if(expectedSourceEpoch<0)throw new MemoryException("MEMORY_REQUEST_INVALID");
  return transactions.execute(tx->{
   var source=mapper.lockSource(b(scope.tenantId()),b(sourceId));var owner=mapper.sourceOwner(b(scope.tenantId()),b(sourceId));
   if(source==null||owner==null||!Arrays.equals(owner.ownerId(),b(actor.userId()))||!scope.domain().equals(owner.domain())||!scope.topLevelAgentId().equals(owner.originTopAgentId()))throw new MemoryException("MEMORY_NOT_FOUND");
   var anchor=memories.findItemForUpdate(source.tenantId(),owner.itemId());requireOwned(anchor,scope);
   var dependencies=List.copyOf(mapper.listSourceDependencies(source.tenantId(),source.id()));
   if(mapper.countSourceSuppression(source.tenantId(),source.id(),source.sourceVersion())>0)return new InvalidationResponse(sourceId,source.sourceEpoch(),dependencies.size(),"REVOKED");
   if(source.sourceEpoch()!=expectedSourceEpoch)throw new MemoryException("MEMORY_REVISION_CONFLICT");
   // 只有来源所有者可以触发全派生撤销；不向HTTP暴露其他派生物的身份或正文。
   var ids=new TreeMap<String,byte[]>();for(var dependency:dependencies)if("MEMORY_VERSION".equals(dependency.targetType()))ids.put(HexFormat.of().formatHex(dependency.targetId()),dependency.targetId());
   var items=new ArrayList<MemoryItemPO>();for(var id:ids.values()){var item=memories.findItemForUpdate(source.tenantId(),id);if(item==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");items.add(item);}
   one(mapper.revokeSource(source));mapper.insertSourceSuppression(anchor,source,uuid());
   // tombstone是GREATEST upsert，合法更新影响2行，不按CAS单行判定。
   memories.advanceTombstone(source.tenantId(),"SOURCE",source.id(),source.deletionEpoch()+1,source.grantEpoch()+1,source.sourceEpoch()+1);
   for(var item:items){
    if(Set.of("DELETE_PENDING","DELETED").contains(item.lifecycle()))continue;
    one(mapper.revokeItem(item));mapper.revokeVersions(item.tenantId(),item.id(),item.grantEpoch()+1,item.sourceEpoch()+1,item.deletionEpoch()+1);
    memories.advanceTombstone(item.tenantId(),"MEMORY_ITEM",item.id(),item.deletionEpoch()+1,item.grantEpoch()+1,item.sourceEpoch()+1);
    byte[] jobId=uuid();var state=new CleanupState(text(jobId),"SOURCE_INVALIDATION",null,0,dependencies,Map.of());
    one(mapper.insertJob(new JobPO(item.tenantId(),jobId,item.id(),item.deletionEpoch()+1,null,item.ownerId(),"QUEUED",6,0,0,0,Instant.now().plusSeconds(86400),encode(state))));
    one(memories.insertOutbox(item.tenantId(),jobId,item.id(),item.currentVersionId()==null?new byte[0]:item.currentVersionId(),"MEMORY_SOURCE_REVOKED",item.deletionEpoch()+1));
   }
   // 没有MEMORY_VERSION目标仍必须持久发布完整source事件，不根据展示引用猜测没有执行/历史依赖。
   one(memories.insertOutbox(source.tenantId(),uuid(),source.id(),source.sourceVersion(),"SOURCE_REVOKED",source.deletionEpoch()+1));
   return new InvalidationResponse(sourceId,source.sourceEpoch()+1,dependencies.size(),"REVOKED");
  });
 }
 public void principalLeftProject(IdentityFacade.Subject actor,MemoryScopeDTO scope){forget.authorize(actor,scope);throw new MemoryException("FEATURE_DISABLED");}
 public void withdrawSharing(IdentityFacade.Subject actor,MemoryScopeDTO scope){forget.authorize(actor,scope);throw new MemoryException("FEATURE_DISABLED");}
 public record InvalidationResponse(String sourceId,long sourceEpoch,int affectedTargets,String status){}
}
