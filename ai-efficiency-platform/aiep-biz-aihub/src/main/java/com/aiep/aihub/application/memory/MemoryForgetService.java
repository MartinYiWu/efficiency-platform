package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.repository.memory.MemoryForgetMapper;
import com.aiep.aihub.repository.memory.MemoryForgetMapper.*;
import com.aiep.identity.api.IdentityFacade;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 先撤销读取再排队清理；外部确认不在事务内，逻辑anchor与最小防复活元数据永久保留。 */
@Service
public class MemoryForgetService {
 private final MemoryMapper memories;private final MemoryForgetMapper mapper;private final MemoryScopePolicy scopes;
 private final MemorySessionBindingService bindings;private final MemoryValueCodec codec;private final TransactionTemplate transactions;
 static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
 public MemoryForgetService(MemoryMapper memories,MemoryForgetMapper mapper,MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryValueCodec codec,PlatformTransactionManager manager){this.memories=memories;this.mapper=mapper;this.scopes=scopes;this.bindings=bindings;this.codec=codec;this.transactions=new TransactionTemplate(manager);}
 public JobResponse forget(IdentityFacade.Subject actor,ForgetCommand command){
  if(command==null||command.expectedRevision()<0)throw new MemoryException("MEMORY_REQUEST_INVALID");
  if(!"FORGET_AND_SUPPRESS".equals(command.mode()))throw new MemoryException("FEATURE_DISABLED");
  b(command.itemId());b(command.idempotencyKey());authorize(actor,command.scope());
  try{return transactions.execute(tx->forgetTransaction(actor,command));}
  catch(DuplicateKeyException race){return transactions.execute(tx->{var prior=memories.findPreferenceDecision(b(command.scope().tenantId()),b(command.idempotencyKey()));if(prior==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");return replay(actor,command,prior);});}
 }
 private JobResponse forgetTransaction(IdentityFacade.Subject actor,ForgetCommand command){
  var scope=command.scope();byte[] tenant=b(scope.tenantId()),id=b(command.itemId());
  // 来源锚点先于item；并发更正若增加来源，回滚重试，绝不漏掉新闭包。
  var candidates=mapper.listItemSources(tenant,id);var locked=new ArrayList<SourcePO>();
  for(var source:candidates){var current=mapper.lockSource(tenant,source.id());if(current==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");locked.add(current);}
  var item=memories.findItemForUpdate(tenant,id);requireOwned(item,scope);
  var prior=memories.findPreferenceDecision(tenant,b(command.idempotencyKey()));if(prior!=null)return replay(actor,command,prior);
  // 初次候选查询可能建立RR旧快照；锁后的集合与闭包必须current read，外层RR事务也不能漏刚提交的边。
  var currentSources=new HashSet<String>();for(var source:mapper.listItemSourceIdsCurrent(tenant,id))currentSources.add(Base64.getEncoder().encodeToString(source.sourceId()));
  if(!sourceKeys(locked).equals(currentSources))throw new MemoryException("MEMORY_REVISION_CONFLICT");
  if(Set.of("DELETE_PENDING","DELETED").contains(item.lifecycle())){var existing=mapper.findItemJob(tenant,id,item.deletionEpoch());if(existing==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");return response(item,existing);}
  if(command.expectedRevision()!=item.revision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  for(var source:locked){var owner=mapper.sourceOwner(tenant,source.id());if(owner==null||!Arrays.equals(owner.ownerId(),item.ownerId())||!item.domain().equals(owner.domain())||!item.originTopAgentId().equals(owner.originTopAgentId()))throw new MemoryException("FEATURE_DISABLED");}
  var dependencies=locked.isEmpty()?List.<DependencyPO>of():List.copyOf(mapper.listSourcesDependenciesCurrent(tenant,locked.stream().map(SourcePO::id).toList()));
  byte[] decision=b(UUID.randomUUID()+"."+fingerprint(actor,command));
  one(memories.insertPreferenceDecision(new DecisionPO(tenant,decision,id,item.currentVersionId(),b(actor.userId()),"FORGET",b(command.idempotencyKey()),item.revision(),item.revision()+1)));
  one(mapper.revokeItem(item));
  mapper.revokeVersions(tenant,id,item.grantEpoch()+1,item.sourceEpoch()+1,item.deletionEpoch()+1);
  mapper.insertFieldSuppression(item,uuid());var suppression=mapper.findFieldSuppression(item);
  if(suppression==null||!suppression.active())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  for(var source:locked){one(mapper.revokeSource(source));mapper.insertSourceSuppression(item,source,uuid());memories.advanceTombstone(tenant,"SOURCE",source.id(),source.deletionEpoch()+1,source.grantEpoch()+1,source.sourceEpoch()+1);}
  // GREATEST upsert成功可返回0/1/2；它是单调防复活写入，不是预期单行的CAS。
  memories.advanceTombstone(tenant,"MEMORY_ITEM",id,item.deletionEpoch()+1,item.grantEpoch()+1,item.sourceEpoch()+1);
  byte[] jobId=uuid();var state=new CleanupState(text(jobId),fingerprint(actor,command),text(suppression.id()),suppression.epoch(),dependencies,Map.of());
  var job=new JobPO(tenant,jobId,id,item.deletionEpoch()+1,b(command.idempotencyKey()),b(actor.userId()),"QUEUED",6,0,0,0,Instant.now().plusSeconds(86400),encode(state));
  one(mapper.insertJob(job));one(memories.insertOutbox(tenant,jobId,id,item.currentVersionId()==null?new byte[0]:item.currentVersionId(),"MEMORY_FORGET",item.deletionEpoch()+1));
  revokeDependentItems(tenant,dependencies,Set.of(HexFormat.of().formatHex(id)));
  return new JobResponse(text(jobId),text(id),"DELETE_PENDING",job.status(),item.revision()+1,job.deletionEpoch(),state.suppressionId(),state.suppressionRevision(),6,0);
 }
 void revokeDependentItems(byte[] tenant,List<DependencyPO> dependencies,Set<String> excluded){
  var targets=new TreeMap<String,byte[]>();for(var dependency:dependencies)if("MEMORY_VERSION".equals(dependency.targetType())){String key=HexFormat.of().formatHex(dependency.targetId());if(!excluded.contains(key))targets.put(key,dependency.targetId());}
  for(var target:targets.values()){
   var item=memories.findItemForUpdate(tenant,target);if(item==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");
   if(Set.of("DELETE_PENDING","DELETED").contains(item.lifecycle()))continue;
   one(mapper.revokeItem(item));mapper.revokeVersions(tenant,item.id(),item.grantEpoch()+1,item.sourceEpoch()+1,item.deletionEpoch()+1);
   memories.advanceTombstone(tenant,"MEMORY_ITEM",item.id(),item.deletionEpoch()+1,item.grantEpoch()+1,item.sourceEpoch()+1);
   byte[] jobId=uuid();var state=new CleanupState(text(jobId),"SOURCE_INVALIDATION",null,0,dependencies,Map.of());
   one(mapper.insertJob(new JobPO(tenant,jobId,item.id(),item.deletionEpoch()+1,null,item.ownerId(),"QUEUED",6,0,0,0,Instant.now().plusSeconds(86400),encode(state))));
   one(memories.insertOutbox(tenant,jobId,item.id(),item.currentVersionId()==null?new byte[0]:item.currentVersionId(),"MEMORY_DERIVED_REVOKED",item.deletionEpoch()+1));
  }
 }
 private JobResponse replay(IdentityFacade.Subject actor,ForgetCommand command,DecisionPO prior){
  String record=text(prior.id()),expected=fingerprint(actor,command);int dot=record.lastIndexOf('.');
  if(!"FORGET".equals(prior.decisionType())||!Arrays.equals(prior.actorId(),b(actor.userId()))||!Arrays.equals(prior.itemId(),b(command.itemId()))||dot<0||!MessageDigest.isEqual(record.substring(dot+1).getBytes(StandardCharsets.US_ASCII),expected.getBytes(StandardCharsets.US_ASCII)))throw new MemoryException("MEMORY_IDEMPOTENCY_CONFLICT");
  var item=memories.findItemForUpdate(b(command.scope().tenantId()),prior.itemId());requireOwned(item,command.scope());
  // 回放原request必须定位其原job；重授权后再次忘记不可把新代job伪装为旧成功。
  var job=mapper.findJob(b(command.scope().tenantId()),findOriginalJob(item,command));
  if(job==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");return response(item,job);
 }
 private byte[] findOriginalJob(MemoryItemPO item,ForgetCommand command){
  var job=mapper.findRequestedJob(item.tenantId(),item.id(),b(command.idempotencyKey()));
  if(job==null||!Arrays.equals(job.requestId(),b(command.idempotencyKey())))throw new MemoryException("MEMORY_IDEMPOTENCY_CONFLICT");return job.id();
 }
 public JobResponse get(IdentityFacade.Subject actor,MemoryScopeDTO scope,String jobId){authorize(actor,scope);return transactions.execute(tx->{var read=mapper.readJob(b(scope.tenantId()),b(jobId));if(read==null)throw new MemoryException("MEMORY_NOT_FOUND");var item=memories.findItemForUpdate(read.tenantId(),read.itemId());requireOwned(item,scope);var job=mapper.findJob(read.tenantId(),read.id());if(!Arrays.equals(job.requestedBy(),b(actor.userId())))throw new MemoryException("MEMORY_NOT_FOUND");return response(item,job);});}
 void authorize(IdentityFacade.Subject actor,MemoryScopeDTO scope){scopes.require(actor,scope,Set.of());bindings.require(actor,scope);}
 static void requireOwned(MemoryItemPO item,MemoryScopeDTO scope){if(item==null||!Arrays.equals(item.tenantId(),b(scope.tenantId()))||!Arrays.equals(item.ownerId(),b(scope.userId()))||!Arrays.equals(item.subjectId(),b(scope.userId()))||!"USER".equals(item.subjectType())||!scope.domain().equals(item.domain())||!scope.topLevelAgentId().equals(item.originTopAgentId())||!"USER_PRIVATE".equals(item.scopeType())||!Arrays.equals(item.scopeId(),MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()))||!"assistant_response".equals(item.purpose()))throw new MemoryException("MEMORY_NOT_FOUND");}
 private String fingerprint(IdentityFacade.Subject actor,ForgetCommand command){return HexFormat.of().formatHex(codec.hmac(b(command.scope().tenantId()),"forget",actor.userId(),command.scope().domain(),command.scope().topLevelAgentId(),command.itemId(),Long.toString(command.expectedRevision()),command.idempotencyKey(),command.mode()));}
 static Set<String> sourceKeys(List<SourcePO> sources){var keys=new HashSet<String>();for(var source:sources)keys.add(Base64.getEncoder().encodeToString(source.id()));return keys;}
 static JobResponse response(MemoryItemPO item,JobPO job){var state=decode(job.receipts());return new JobResponse(text(job.id()),text(item.id()),item.lifecycle(),job.status(),item.revision(),job.deletionEpoch(),state.suppressionId(),state.suppressionRevision(),job.requiredTargets(),job.completedTargets());}
 static String encode(CleanupState state){try{return JSON.writeValueAsString(state);}catch(Exception error){throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");}}
 static CleanupState decode(String value){try{return JSON.readValue(value,CleanupState.class);}catch(Exception error){throw new MemoryException("MEMORY_STORAGE_UNAVAILABLE");}}
 static void one(int rows){MemoryVersionService.requireOne(rows);}
 static byte[] b(String value){return MemoryMapper.identity(value);}
 static byte[] uuid(){return b(UUID.randomUUID().toString());}
 static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
 public record ForgetCommand(MemoryScopeDTO scope,String itemId,long expectedRevision,String idempotencyKey,String mode){}
 public record JobResponse(String jobId,String itemId,String status,String jobStatus,long revision,long deletionEpoch,String suppressionId,long suppressionRevision,int requiredTargets,int completedTargets){}
 record CleanupState(String eventId,String requestFingerprint,String suppressionId,long suppressionRevision,List<DependencyPO> dependencies,Map<String,String> receipts){}
}
