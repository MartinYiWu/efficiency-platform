package com.aiep.aihub.memory;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.aihub.repository.memory.MemoryMapper.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.identity.api.IdentityFacade;
import java.util.*;
import java.security.SecureRandom;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class MemoryPreferenceTest {
 final MemoryMapper mapper=mock(MemoryMapper.class);
 final MemoryScopePolicy scopes=mock(MemoryScopePolicy.class);
 final MemorySessionBindingService bindings=mock(MemorySessionBindingService.class);
 final PlatformTransactionManager manager=mock(PlatformTransactionManager.class);
 final MemoryValueCodec codec=codec();
 final MemoryPolicyService policy=new MemoryPolicyService(mapper);
 final MemoryPreferenceService service=new MemoryPreferenceService(mapper,scopes,bindings,policy,new MemoryVersionService(mapper,codec),codec,manager);
 final IdentityFacade.Subject actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original");
 final MemoryScopeDTO scope=new MemoryScopeDTO("t","u","operations","operations","CONVERSATION","s");
 MemoryItemPO item;VersionRow row;DecisionPO decision;
 static byte[] b(String v){return MemoryMapper.identity(v);}
 static MemoryValueCodec codec(){byte[] key=new byte[32],mac=new byte[32];new SecureRandom().nextBytes(key);new SecureRandom().nextBytes(mac);return new MemoryValueCodec("test","{\"test\":\""+Base64.getEncoder().encodeToString(key)+"\"}",Base64.getEncoder().encodeToString(mac));}
 PreferenceCommand command(String value,long revision,String key){return new PreferenceCommand(scope,"response.language",value,revision,key,null);}
 void enabled(){
  when(manager.getTransaction(any())).thenAnswer(i->new SimpleTransactionStatus());
  String json="{\"fields\":{\"response.language\":{\"enabled\":true,\"values\":[\"zh-CN\",\"en-US\"],\"retentionSeconds\":3600,\"sourceRetentionSeconds\":1200}}}";
  when(mapper.findPublishedPolicy(any(),eq("operations"))).thenReturn(new PolicyPO(b("policy"),b("p1"),json,new byte[32],"memory-policy/1"));
  when(mapper.findPolicyVersion(any(),any(),any())).thenReturn(new PolicyPO(b("policy"),b("p1"),MemoryArtifactPolicyTest.withArtifacts(json),new byte[32],"memory-policy/1"));
  when(mapper.findPreferenceItem(any(),any(),any(),any())).thenAnswer(i->item);
  when(mapper.findItemForUpdate(any(),any())).thenAnswer(i->item);
  when(mapper.findPreferenceVersion(any(),any(),any())).thenAnswer(i->row);
  when(mapper.insertItem(any())).thenAnswer(i->{item=i.getArgument(0);return 1;});
  when(mapper.insertPreferenceDecision(any())).thenAnswer(i->{decision=i.getArgument(0);return 1;});
  when(mapper.insertPreferenceVersion(any())).thenAnswer(i->{row=i.getArgument(0);return 1;});
  when(mapper.insertPreferenceSource(any(),any(),any(),any(),any())).thenReturn(1);
  when(mapper.insertPreferenceDependency(any(),any(),any(),any())).thenReturn(1);
  when(mapper.clearPreferenceCurrent(any(),any(),anyLong(),any())).thenReturn(1);
  when(mapper.retirePreferenceVersion(any(),any(),any())).thenReturn(1);
  when(mapper.compareAndSetCurrent(any(),any(),anyLong(),any(),any())).thenAnswer(i->{item=new MemoryItemPO(item.tenantId(),item.id(),item.subjectType(),item.subjectId(),item.ownerId(),item.domain(),item.originTopAgentId(),item.scopeType(),item.scopeId(),item.purpose(),item.fieldKey(),"LIVE",item.revision()+1,i.getArgument(3),0,0,0);return 1;});
 }
 @Test void missingArtifactContractCannotCreatePersistentVersion(){enabled();
  when(mapper.findPolicyVersion(any(),any(),any())).thenReturn(new PolicyPO(b("policy"),b("p1"),"{}",new byte[32],"memory-policy/1"));
  assertCode("FEATURE_DISABLED",()->service.save(actor,command("zh-CN",0,"missing-artifacts")));
  verify(mapper,never()).insertPreferenceVersion(any());
 }
 @Test void explicitPreferenceReachesEncryptedPersistenceAndOriginalAuthorization(){enabled();
  var result=new DefaultMemoryFacade(scopes,bindings,service).savePreference(actor,command("zh-CN",0,"request"));
  assertEquals("zh-CN",result.value());assertEquals(1,result.revision());assertEquals("ACTIVE",result.status());
  assertFalse(Arrays.equals(b("zh-CN"),row.encryptedPayload()));assertEquals(12,row.nonce().length);assertEquals(16,row.authTag().length);
  assertTrue(result.expiresAt().isBefore(Instant.now().plusSeconds(1201)));assertFalse(result.sourceRef().contains("."));verify(bindings,atLeastOnce()).require(actor,scope);
 }
 @Test void correctionRetiresBeforeInsertAndCasAndRejectPreservesActive(){enabled();service.save(actor,command("zh-CN",0,"save"));clearInvocations(mapper);
  var corrected=service.correct(actor,new String(item.id()),command("en-US",1,"correct"));assertEquals(2,corrected.revision());
  var order=inOrder(mapper);order.verify(mapper).clearPreferenceCurrent(any(),any(),eq(1L),any());order.verify(mapper).retirePreferenceVersion(any(),any(),any());order.verify(mapper).insertPreferenceVersion(any());order.verify(mapper).compareAndSetCurrent(any(),any(),eq(1L),any(),eq("LIVE"));
  clearInvocations(mapper);var rejected=service.decide(actor,new String(item.id()),command("en-US",2,"reject"),"REJECT");assertEquals(corrected.versionId(),rejected.versionId());assertEquals("REJECT",decision.decisionType());verify(mapper,never()).insertPreferenceVersion(any());
 }
 @Test void idempotencyBindsValueActionActorAndExpectedRevision(){enabled();var first=service.save(actor,command("zh-CN",0,"same"));when(mapper.findPreferenceDecision(any(),any())).thenAnswer(i->decision);
  assertEquals(first,service.save(actor,command("zh-CN",0,"same")));
  assertCode("MEMORY_IDEMPOTENCY_CONFLICT",()->service.save(actor,command("en-US",0,"same")));
  assertCode("MEMORY_IDEMPOTENCY_CONFLICT",()->service.save(actor,command("zh-CN",1,"same")));
  var other=new IdentityFacade.Subject("t","other",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"other");assertCode("MEMORY_IDEMPOTENCY_CONFLICT",()->service.save(other,command("zh-CN",0,"same")));
 }
 @Test void wrongRevisionOtherAgentAndNonLiveCannotReadOrOverwrite(){enabled();service.save(actor,command("zh-CN",0,"first"));
  assertCode("MEMORY_REVISION_CONFLICT",()->service.correct(actor,new String(item.id()),command("en-US",0,"wrong")));
  assertCode("MEMORY_NOT_FOUND",()->service.get(actor,new MemoryScopeDTO("t","u","hr","hr","TASK_ONLY",null),new String(item.id())));
  item=new MemoryItemPO(item.tenantId(),item.id(),item.subjectType(),item.subjectId(),item.ownerId(),item.domain(),item.originTopAgentId(),item.scopeType(),item.scopeId(),item.purpose(),item.fieldKey(),"REVOKED",item.revision(),item.currentVersionId(),0,0,0);
  assertCode("MEMORY_NOT_FOUND",()->service.get(actor,scope,new String(item.id())));
 }
 @Test void disabledPolicyUnknownFieldBadValueAndMissingKeyFailClosed(){assertCode("FEATURE_DISABLED",()->policy.require(scope,"response.language","zh-CN"));assertCode("FEATURE_DISABLED",()->policy.require(scope,"unknown","zh-CN"));enabled();assertCode("MEMORY_VALUE_INVALID",()->service.save(actor,command("free text",0,"bad")));assertCode("MEMORY_KEY_UNAVAILABLE",()->new MemoryValueCodec("","","").currentVersion());}
 @Test void formatOnlyPublishedPolicyCanList(){enabled();
  String json="{\"fields\":{\"response.format\":{\"enabled\":true,\"values\":[\"table\"],\"retentionSeconds\":90,\"sourceRetentionSeconds\":30}}}";
  when(mapper.findPublishedPolicy(any(),any())).thenReturn(new PolicyPO(b("policy"),b("format-only"),json,new byte[32],"memory-policy/1"));
  assertTrue(service.list(actor,scope,Set.of()).isEmpty());
 }
 @Test void getAndHistoryPreservePersistedExpiryWithoutWriting(){enabled();service.save(actor,command("zh-CN",0,"save"));when(mapper.listPreferenceVersions(any(),any())).thenAnswer(i->List.of(row));clearInvocations(mapper);var result=service.get(actor,scope,new String(item.id()));assertEquals(row.expiresAt(),result.preference().expiresAt());assertEquals(row.expiresAt(),result.history().get(0).expiresAt());verify(mapper,never()).insertPreferenceVersion(any());verify(mapper,never()).compareAndSetCurrent(any(),any(),anyLong(),any(),any());}
 @Test void aesGcmRandomNonceTenantHmacAndAllAadDimensions(){var one=codec.seal(b("t"),b("i"),b("v"),"zh-CN");var two=codec.seal(b("t"),b("i"),b("v"),"zh-CN");assertFalse(Arrays.equals(one.nonce(),two.nonce()));assertFalse(Arrays.equals(codec.hmac(b("t"),"value","zh-CN"),codec.hmac(b("other"),"value","zh-CN")));
  for(String changed:List.of("tenant","item","version")){var bad=new VersionRow(b(changed.equals("tenant")?"other":"t"),b(changed.equals("item")?"other":"i"),b(changed.equals("version")?"other":"v"),"ACTIVE",one.payload(),one.keyVersion(),one.nonce(),one.tag(),one.hmac(),null,null,null,null,Instant.now().plusSeconds(1),1);assertCode("MEMORY_KEY_UNAVAILABLE",()->codec.open(bad));}}
 static void assertCode(String expected,org.junit.jupiter.api.function.Executable action){assertEquals(expected,assertThrows(MemoryException.class,action).code());}
}
