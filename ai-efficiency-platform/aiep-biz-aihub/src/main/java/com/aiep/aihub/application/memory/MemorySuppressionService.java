package com.aiep.aihub.application.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.identity.api.IdentityFacade;
import java.time.Instant;
import java.util.*;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static com.aiep.aihub.application.memory.MemoryForgetService.*;

/** 用户明确新值和确认语义才解除同字段抑制；不解除旧SOURCE规则，不复活任何旧版本。 */
@Service
public class MemorySuppressionService {
 private final MemoryMapper memories;private final MemoryForgetMapper mapper;private final MemoryForgetService forget;
 private final MemoryPolicyService policies;private final MemoryValueCodec codec;private final TransactionTemplate transactions;
 public MemorySuppressionService(MemoryMapper memories,MemoryForgetMapper mapper,MemoryForgetService forget,MemoryPolicyService policies,MemoryValueCodec codec,PlatformTransactionManager manager){this.memories=memories;this.mapper=mapper;this.forget=forget;this.policies=policies;this.codec=codec;this.transactions=new TransactionTemplate(manager);}
 public Preference reauthorize(IdentityFacade.Subject actor,String suppressionId,ReauthorizationCommand command){
  if(command==null||command.expectedRevision()<0||command.expectedSuppressionRevision()<1||!"ALLOW_REMEMBER".equals(command.confirmation()))throw new MemoryException("MEMORY_REQUEST_INVALID");
  b(suppressionId);b(command.itemId());b(command.idempotencyKey());forget.authorize(actor,command.scope());
  var policy=policies.require(command.scope(),command.fieldKey(),command.value());codec.currentVersion();
  try{return transactions.execute(tx->write(actor,suppressionId,command,policy,false));}
  catch(DuplicateKeyException collision){return transactions.execute(tx->write(actor,suppressionId,command,policy,true));}
 }
 private Preference write(IdentityFacade.Subject actor,String suppressionId,ReauthorizationCommand command,MemoryPolicyService.Published policy,boolean replayOnly){
  var scope=command.scope();var item=memories.findItemForUpdate(b(scope.tenantId()),b(command.itemId()));requireOwned(item,scope);
  if(!item.fieldKey().equals(command.fieldKey()))throw new MemoryException("MEMORY_NOT_FOUND");
  String fingerprint=HexFormat.of().formatHex(codec.hmac(item.tenantId(),"reauthorize",actor.userId(),scope.domain(),scope.topLevelAgentId(),command.itemId(),suppressionId,command.fieldKey(),command.value(),Long.toString(command.expectedRevision()),Long.toString(command.expectedSuppressionRevision()),command.idempotencyKey(),command.confirmation()));
  var prior=memories.findPreferenceDecision(item.tenantId(),b(command.idempotencyKey()));
  if(prior!=null){
   String id=text(prior.id());int dot=id.lastIndexOf('.');
   if(dot<0||!"REAUTHORIZE".equals(prior.decisionType())||!Arrays.equals(prior.actorId(),b(actor.userId()))||!Arrays.equals(prior.itemId(),item.id())||!MessageDigest.isEqual(id.substring(dot+1).getBytes(StandardCharsets.US_ASCII),fingerprint.getBytes(StandardCharsets.US_ASCII)))throw new MemoryException("MEMORY_IDEMPOTENCY_CONFLICT");
   var row=memories.findPreferenceVersion(item.tenantId(),item.id(),prior.targetVersionId());
   if(!"LIVE".equals(item.lifecycle())||row==null||!Set.of("ACTIVE","SUPERSEDED").contains(row.status())||row.expiresAt()==null||!row.expiresAt().isAfter(Instant.now()))throw new MemoryException("MEMORY_NOT_FOUND");
   return project(scope,item,row);
  }
  if(replayOnly||!"DELETED".equals(item.lifecycle())||item.currentVersionId()!=null||item.revision()!=command.expectedRevision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  MemoryPolicyService.requireArtifactPolicy(memories.findPolicyVersion(item.tenantId(),policy.id(),policy.versionId()));
  var job=mapper.findItemJob(item.tenantId(),item.id(),item.deletionEpoch());
  if(job==null||!"SUCCEEDED".equals(job.status())||job.requiredTargets()!=job.completedTargets())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  var suppression=mapper.findFieldSuppression(item);
  if(suppression==null||!Arrays.equals(suppression.id(),b(suppressionId))||!suppression.active()||suppression.epoch()!=command.expectedSuppressionRevision())throw new MemoryException("MEMORY_REVISION_CONFLICT");
  byte[] version=uuid(),decision=b(UUID.randomUUID()+"."+fingerprint);long revision=item.revision()+1,grant=item.grantEpoch()+1;
  one(mapper.deactivateSuppression(item.tenantId(),suppression.id(),suppression.epoch()));
  one(mapper.insertReauthorizationDecision(new DecisionPO(item.tenantId(),decision,item.id(),version,b(actor.userId()),"REAUTHORIZE",b(command.idempotencyKey()),item.revision(),revision),suppression.epoch()));
  var sealed=codec.seal(item.tenantId(),item.id(),version,command.value());var expires=Instant.now().plusSeconds(policy.retentionSeconds());
  var row=new VersionRow(item.tenantId(),item.id(),version,"ACTIVE",sealed.payload(),sealed.keyVersion(),sealed.nonce(),sealed.tag(),sealed.hmac(),policy.id(),policy.versionId(),decision,null,expires,revision);
  one(mapper.insertReauthorizedVersion(row,grant,item.sourceEpoch(),item.deletionEpoch()));
  byte[] source=uuid();one(mapper.insertReauthorizedSource(item.tenantId(),source,decision,version,expires,grant,item.sourceEpoch(),item.deletionEpoch()));
  one(mapper.insertReauthorizedDependency(item.tenantId(),source,item.id(),version,grant,item.sourceEpoch(),item.deletionEpoch()));
  one(mapper.reauthorizeItem(item,version));return project(scope,item,row);
 }
 private Preference project(MemoryScopeDTO scope,MemoryItemPO item,VersionRow row){String decision=text(row.decisionId());int dot=decision.indexOf('.');return new Preference(text(item.id()),text(row.id()),scope,item.fieldKey(),codec.open(row),row.revision(),row.status(),"USER_PREFERENCE_DECISION",dot<0?decision:decision.substring(0,dot),row.expiresAt());}
 public record ReauthorizationCommand(MemoryScopeDTO scope,String itemId,String fieldKey,String value,long expectedRevision,long expectedSuppressionRevision,String idempotencyKey,String confirmation){}
}
