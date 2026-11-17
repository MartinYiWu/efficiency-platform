package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.identity.api.IdentityFacade;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 确定性用户输入，授权后短事务；唯一冲突仅在整个失败事务回滚后有限回读一次。 */
@Service
public class MemoryPreferenceService {
 private final MemoryMapper mapper;private final MemoryScopePolicy scopes;private final MemorySessionBindingService bindings;
 private final MemoryPolicyService policies;private final MemoryVersionService versions;private final MemoryValueCodec codec;private final TransactionTemplate transactions;
 public MemoryPreferenceService(MemoryMapper mapper,MemoryScopePolicy scopes,MemorySessionBindingService bindings,MemoryPolicyService policies,MemoryVersionService versions,MemoryValueCodec codec,PlatformTransactionManager manager){
  this.mapper=mapper;this.scopes=scopes;this.bindings=bindings;this.policies=policies;this.versions=versions;this.codec=codec;this.transactions=new TransactionTemplate(manager);
 }
 private void authorize(IdentityFacade.Subject actor,MemoryScopeDTO scope,Set<String> fields){scopes.require(actor,scope,fields);bindings.require(actor,scope);}
 public List<Preference> list(IdentityFacade.Subject actor,MemoryScopeDTO scope,Set<String> fields){
  authorize(actor,scope,fields);
  return transactions.execute(status->{
   boolean enabled=false;
   for(String field:List.of("response.language","response.detail_level","response.format")) {
    try {policies.require(scope,field,null);enabled=true;}catch(MemoryException failure){if(!"FEATURE_DISABLED".equals(failure.code()))throw failure;}
   }
   if(!enabled)throw new MemoryException("FEATURE_DISABLED");
   List<Preference> result=new ArrayList<>();
   // 本人/Agent/固定三字段已在SQL内限定；发布策略再决定可用字段，total只基于这个授权结果。
   for(var item:mapper.listPreferenceItems(bytes(scope.tenantId()),bytes(scope.userId()),scope.domain())){
    if(!fields.isEmpty()&&!fields.contains(item.fieldKey()))continue;
    try{policies.require(scope,item.fieldKey(),null);}catch(MemoryException failure){if("FEATURE_DISABLED".equals(failure.code()))continue;throw failure;}
    var row=mapper.findPreferenceVersion(item.tenantId(),item.id(),item.currentVersionId());
    if(readable(row)&&"ACTIVE".equals(row.status()))result.add(project(item,row,scope));
   }
   // 缺发布策略时即使没有记录也明确422，不把未启用伪装为空成功。
   for(String field:fields)policies.require(scope,field,null);
   return List.copyOf(result);
  });
 }
 public PreferenceHistory get(IdentityFacade.Subject actor,MemoryScopeDTO scope,String id){
  authorize(actor,scope,Set.of());return transactions.execute(status->{
   var item=owned(scope,id);policies.require(scope,item.fieldKey(),null);
   if(!"LIVE".equals(item.lifecycle()))throw new MemoryException("MEMORY_NOT_FOUND");
   var current=mapper.findPreferenceVersion(item.tenantId(),item.id(),item.currentVersionId());
   if(!readable(current)||!"ACTIVE".equals(current.status()))throw new MemoryException("MEMORY_NOT_FOUND");
   List<Preference> history=new ArrayList<>();for(var row:mapper.listPreferenceVersions(item.tenantId(),item.id()))if(readable(row))history.add(project(item,row,scope));
   return new PreferenceHistory(project(item,current,scope),history);
  });
 }
 public Preference save(IdentityFacade.Subject actor,PreferenceCommand command){return write(actor,null,command,"SAVE");}
 public Preference correct(IdentityFacade.Subject actor,String id,PreferenceCommand command){return write(actor,id,command,"CORRECT");}
 public Preference decide(IdentityFacade.Subject actor,String id,PreferenceCommand command,String action){
  if(!Set.of("CONFIRM","REJECT").contains(action))throw new MemoryException("FEATURE_DISABLED");return write(actor,id,command,action);
 }
 private Preference write(IdentityFacade.Subject actor,String id,PreferenceCommand command,String action){
  if(command==null||command.fieldKey()==null||command.value()==null||command.expectedRevision()<0||command.expectedSuppressionRevision()!=null)throw new MemoryException("MEMORY_REQUEST_INVALID");
  bytes(command.idempotencyKey());authorize(actor,command.scope(),Set.of(command.fieldKey()));
  var policy=policies.require(command.scope(),command.fieldKey(),command.value());codec.currentVersion();
  try{return transactions.execute(status->writeTransaction(actor,id,command,action,policy,false));}
  catch(DuplicateKeyException duplicate){return transactions.execute(status->writeTransaction(actor,id,command,action,policy,true));}
 }
 private Preference writeTransaction(IdentityFacade.Subject actor,String id,PreferenceCommand command,String action,MemoryPolicyService.Published policy,boolean winnerOnly){
  var scope=command.scope();byte[] tenant=bytes(scope.tenantId());
  var prior=mapper.findPreferenceDecision(tenant,bytes(command.idempotencyKey()));
  if(prior!=null)return replay(actor,id,command,action,prior);
  var found=id==null?mapper.findPreferenceItem(tenant,bytes(scope.userId()),scope.domain(),command.fieldKey()):owned(scope,id);
  MemoryItemPO item;
  if(found==null){
   if(winnerOnly||!"SAVE".equals(action)||command.expectedRevision()!=0)throw new MemoryException("MEMORY_REVISION_CONFLICT");
   item=new MemoryItemPO(tenant,uuid(),"USER",bytes(scope.userId()),bytes(scope.userId()),scope.domain(),scope.topLevelAgentId(),"USER_PRIVATE",MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()),"assistant_response",command.fieldKey(),"LIVE",0,null,0,0,0);
   MemoryVersionService.requireOne(mapper.insertItem(item));
  }else item=mapper.findItemForUpdate(tenant,found.id());
  requireOwned(item,scope);
  if(!command.fieldKey().equals(item.fieldKey()))throw new MemoryException("MEMORY_SCOPE_DENIED");
  if(!"LIVE".equals(item.lifecycle())||mapper.countPreferenceSuppression(tenant,bytes(scope.userId()),scope.domain(),item.scopeId(),item.fieldKey())!=0)throw new MemoryException("FEATURE_DISABLED");
  VersionRow current=item.currentVersionId()==null?null:mapper.findPreferenceVersion(tenant,item.id(),item.currentVersionId());
  if(item.currentVersionId()!=null&&current==null)throw new MemoryException("MEMORY_NOT_FOUND");
  boolean same=readable(current)&&MessageDigest.isEqual(current.contentHmac(),codec.hmac(tenant,"value",command.value()));
  boolean unchanged="SAVE".equals(action)&&same;
  if(!unchanged&&command.expectedRevision()!=item.revision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  if(("CONFIRM".equals(action)||"REJECT".equals(action))&&(!same||current==null))throw new MemoryException("MEMORY_REVISION_CONFLICT");
  if("SAVE".equals(action)&&current!=null&&!same)throw new MemoryException("MEMORY_REVISION_CONFLICT");
  if(winnerOnly&&!unchanged)throw new MemoryException("MEMORY_REVISION_CONFLICT");
  boolean mutate=!unchanged&&!"CONFIRM".equals(action)&&!"REJECT".equals(action);
  if("CORRECT".equals(action)&&current==null)throw new MemoryException("MEMORY_REVISION_CONFLICT");
  byte[] next=mutate?uuid():current.id();long revision=mutate?item.revision()+1:current.revision();
  byte[] decision=bytes(UUID.randomUUID()+"."+HexFormat.of().formatHex(binding(actor,id,command,action)));
  MemoryVersionService.requireOne(mapper.insertPreferenceDecision(new DecisionPO(tenant,decision,item.id(),next,bytes(actor.userId()),action,bytes(command.idempotencyKey()),command.expectedRevision(),revision)));
  var row=mutate?versions.replace(item,next,decision,command.value(),policy):current;
  return project(item,row,scope);
 }
 private Preference replay(IdentityFacade.Subject actor,String id,PreferenceCommand command,String action,DecisionPO prior){
  String decision=text(prior.id());int separator=decision.lastIndexOf('.');
  if(!Arrays.equals(prior.actorId(),bytes(actor.userId()))||!action.equals(prior.decisionType())||separator<0
   ||!MessageDigest.isEqual(decision.substring(separator+1).getBytes(StandardCharsets.US_ASCII),HexFormat.of().formatHex(binding(actor,id,command,action)).getBytes(StandardCharsets.US_ASCII)))throw new MemoryException("MEMORY_IDEMPOTENCY_CONFLICT");
  var item=owned(command.scope(),text(prior.itemId()));if(!"LIVE".equals(item.lifecycle()))throw new MemoryException("MEMORY_NOT_FOUND");if(!item.fieldKey().equals(command.fieldKey()))throw new MemoryException("MEMORY_IDEMPOTENCY_CONFLICT");
  var row=mapper.findPreferenceVersion(item.tenantId(),item.id(),prior.targetVersionId());if(!readable(row))throw new MemoryException("MEMORY_NOT_FOUND");return project(item,row,command.scope());
 }
 private byte[] binding(IdentityFacade.Subject actor,String id,PreferenceCommand command,String action){
  var scope=command.scope();return codec.hmac(bytes(scope.tenantId()),"request",actor.userId(),scope.domain(),scope.topLevelAgentId(),command.fieldKey(),action,id==null?"":id,command.value(),Long.toString(command.expectedRevision()),command.idempotencyKey());
 }
 private MemoryItemPO owned(MemoryScopeDTO scope,String id){var item=mapper.findItemForUpdate(bytes(scope.tenantId()),bytes(id));requireOwned(item,scope);return item;}
 private void requireOwned(MemoryItemPO item,MemoryScopeDTO scope){
  if(item==null||!Arrays.equals(item.tenantId(),bytes(scope.tenantId()))||!Arrays.equals(item.subjectId(),bytes(scope.userId()))||!Arrays.equals(item.ownerId(),bytes(scope.userId()))||!"USER".equals(item.subjectType())||!scope.domain().equals(item.domain())||!scope.topLevelAgentId().equals(item.originTopAgentId())||!"USER_PRIVATE".equals(item.scopeType())||!Arrays.equals(item.scopeId(),MemoryMapper.privateScope(scope.userId(),scope.topLevelAgentId()))||!"assistant_response".equals(item.purpose()))throw new MemoryException("MEMORY_NOT_FOUND");
 }
 private boolean readable(VersionRow row){return row!=null&&Set.of("ACTIVE","SUPERSEDED").contains(row.status())&&row.expiresAt()!=null&&row.expiresAt().isAfter(Instant.now());}
 private Preference project(MemoryItemPO item,VersionRow row,MemoryScopeDTO scope){
  String decision=text(row.decisionId());int separator=decision.indexOf('.');return new Preference(text(item.id()),text(row.id()),scope,item.fieldKey(),codec.open(row),row.revision(),row.status(),"USER_PREFERENCE_DECISION",separator<0?decision:decision.substring(0,separator),row.expiresAt());
 }
 private static byte[] bytes(String value){return MemoryMapper.identity(value);}
 private static byte[] uuid(){return bytes(UUID.randomUUID().toString());}
 private static String text(byte[] value){return new String(value,StandardCharsets.UTF_8);}
}
