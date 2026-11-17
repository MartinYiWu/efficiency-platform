package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper.MemoryItemPO;
import com.aiep.aihub.repository.memory.MemoryForgetMapper.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.identity.api.IdentityFacade;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryForgetTest {
 final MemoryMapper memories=mock(MemoryMapper.class);
 final MemoryForgetMapper mapper=mock(MemoryForgetMapper.class);
 final MemoryScopePolicy scopes=mock(MemoryScopePolicy.class);
 final MemorySessionBindingService bindings=mock(MemorySessionBindingService.class);
 final PlatformTransactionManager manager=mock(PlatformTransactionManager.class);
 final MemoryValueCodec codec=MemoryPreferenceTest.codec();
 final MemoryForgetService service=new MemoryForgetService(memories,mapper,scopes,bindings,codec,manager);
 final IdentityFacade.Subject actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original");
 final MemoryScopeDTO scope=new MemoryScopeDTO("t","u","operations","operations","TASK_ONLY",null);
 static byte[] b(String s){return MemoryMapper.identity(s);}
 MemoryItemPO item(String owner,String lifecycle){return new MemoryItemPO(b("t"),b("item"),"USER",b(owner),b(owner),"operations","operations","USER_PRIVATE",MemoryMapper.privateScope(owner,"operations"),"assistant_response","response.language",lifecycle,1,b("v1"),0,0,0);}
 void fixture(){when(manager.getTransaction(any())).thenReturn(new SimpleTransactionStatus());when(memories.findItemForUpdate(any(),any())).thenReturn(item("u","LIVE"));when(mapper.listItemSources(any(),any())).thenReturn(List.of());when(mapper.listItemSourceIdsCurrent(any(),any())).thenReturn(List.of());when(mapper.listSourcesDependenciesCurrent(any(),any())).thenReturn(List.of());when(mapper.revokeItem(any())).thenReturn(1);when(mapper.revokeVersions(any(),any(),anyLong(),anyLong(),anyLong())).thenReturn(1);when(mapper.insertFieldSuppression(any(),any())).thenReturn(1);when(mapper.findFieldSuppression(any())).thenReturn(new SuppressionPO(b("t"),b("supp"),"FIELD",new byte[0],new byte[0],1,true));when(mapper.insertJob(any())).thenReturn(1);when(memories.insertPreferenceDecision(any())).thenReturn(1);when(memories.advanceTombstone(any(),any(),any(),anyLong(),anyLong(),anyLong())).thenReturn(1);when(memories.insertOutbox(any(),any(),any(),any(),any(),anyLong())).thenReturn(1);}
 @Test void forgetAtomicallyRevokesBeforeQueueAndDoesNotClaimDeletion(){fixture();var job=service.forget(actor,new MemoryForgetService.ForgetCommand(scope,"item",1,"request","FORGET_AND_SUPPRESS"));assertEquals("DELETE_PENDING",job.status());assertEquals(6,job.requiredTargets());assertEquals(0,job.completedTargets());var order=inOrder(mapper,memories);order.verify(mapper).revokeItem(any());order.verify(mapper).revokeVersions(any(),any(),eq(1L),eq(1L),eq(1L));order.verify(mapper).insertFieldSuppression(any(),any());order.verify(memories).advanceTombstone(any(),eq("MEMORY_ITEM"),any(),eq(1L),eq(1L),eq(1L));order.verify(mapper).insertJob(any());order.verify(memories).insertOutbox(any(),any(),any(),any(),eq("MEMORY_FORGET"),eq(1L));verify(bindings).require(actor,scope);}
 @Test void successfulTombstoneUpsertMayReportTwoChangedRowsWithoutBeingACasConflict(){fixture();when(memories.advanceTombstone(any(),any(),any(),anyLong(),anyLong(),anyLong())).thenReturn(2);assertEquals("DELETE_PENDING",service.forget(actor,new MemoryForgetService.ForgetCommand(scope,"item",1,"second-forget","FORGET_AND_SUPPRESS")).status());verify(mapper).insertJob(any());}
 @Test void currentSourceSetChangeFailsClosedBeforeAnyMutationOrOutOfOrderSourceLock(){fixture();when(mapper.listItemSourceIdsCurrent(any(),any())).thenReturn(List.of(new SourceIdPO(b("new-source"))));assertEquals("MEMORY_REVISION_CONFLICT",assertThrows(MemoryException.class,()->service.forget(actor,new MemoryForgetService.ForgetCommand(scope,"item",1,"changed-sources","FORGET_AND_SUPPRESS"))).code());verify(mapper,never()).lockSource(any(),any());verify(mapper,never()).revokeItem(any());verify(mapper,never()).insertJob(any());}
 @Test void missingAndOtherOwnerNeverBecomeFakeSuccessfulForget(){fixture();when(memories.findItemForUpdate(any(),any())).thenReturn(null,item("other","LIVE"));for(int n=0;n<2;n++)assertEquals("MEMORY_NOT_FOUND",assertThrows(MemoryException.class,()->service.forget(actor,new MemoryForgetService.ForgetCommand(scope,"item",1,"request","FORGET_AND_SUPPRESS"))).code());verify(mapper,never()).insertJob(any());}
 @Test void noCleanupPortCannotClaimAnEmptyDependencySetIsClean(){fixture();
  var provider=mock(org.springframework.beans.factory.ObjectProvider.class);
  var cleanup=new MemoryDeletionService(memories,mapper,manager,provider);
  when(mapper.readJob(any(),any())).thenReturn(null);
  assertEquals("MEMORY_NOT_FOUND",assertThrows(MemoryException.class,()->cleanup.compensate("t","missing")).code());
  assertTrue(MemoryDeletionService.Acknowledgement.pending("event",1).receipts().isEmpty());
 }
 @Test void sameKeyReplaysOriginalJobButDifferentRevisionCannotReuseIt(){fixture();
  var decision=new java.util.concurrent.atomic.AtomicReference<MemoryMapper.DecisionPO>();var job=new java.util.concurrent.atomic.AtomicReference<JobPO>();
  when(memories.insertPreferenceDecision(any())).thenAnswer(i->{decision.set(i.getArgument(0));return 1;});when(mapper.insertJob(any())).thenAnswer(i->{job.set(i.getArgument(0));return 1;});
  var command=new MemoryForgetService.ForgetCommand(scope,"item",1,"exact-key","FORGET_AND_SUPPRESS");var first=service.forget(actor,command);
  when(memories.findPreferenceDecision(any(),any())).thenAnswer(i->decision.get());when(mapper.findRequestedJob(any(),any(),any())).thenAnswer(i->job.get());when(mapper.findJob(any(),any())).thenAnswer(i->job.get());
  assertEquals(first.jobId(),service.forget(actor,command).jobId());
  assertEquals("MEMORY_IDEMPOTENCY_CONFLICT",assertThrows(MemoryException.class,()->service.forget(actor,new MemoryForgetService.ForgetCommand(scope,"item",2,"exact-key","FORGET_AND_SUPPRESS"))).code());
  verify(mapper,times(1)).revokeItem(any());verify(mapper,times(1)).insertJob(any());
 }
 @Test void missingExternalPortKeepsRealJobPendingEvenWithNoRegisteredDependencies()throws Exception{fixture();
  var provider=mock(org.springframework.beans.factory.ObjectProvider.class);var cleanup=new MemoryDeletionService(memories,mapper,manager,provider);
  String receipts=new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(Map.of("eventId","job","requestFingerprint","test","suppressionId","supp","suppressionRevision",1,"dependencies",List.of(),"receipts",Map.of()));
  var pending=new JobPO(b("t"),b("job"),b("item"),1,b("request"),b("u"),"QUEUED",6,0,0,0,java.time.Instant.now().plusSeconds(3600),receipts);
  var live=item("u","DELETE_PENDING");var revoked=new MemoryItemPO(live.tenantId(),live.id(),live.subjectType(),live.subjectId(),live.ownerId(),live.domain(),live.originTopAgentId(),live.scopeType(),live.scopeId(),live.purpose(),live.fieldKey(),"DELETE_PENDING",2,null,1,1,1);when(memories.findItemForUpdate(any(),any())).thenReturn(revoked);when(mapper.readJob(any(),any())).thenReturn(pending);when(mapper.findJob(any(),any())).thenReturn(pending);when(mapper.updateJob(any(),anyLong())).thenReturn(1);
  cleanup.compensate("t","job");var saved=org.mockito.ArgumentCaptor.forClass(JobPO.class);verify(mapper,times(2)).updateJob(saved.capture(),anyLong());assertEquals("BLOCKED",saved.getValue().status());assertEquals(0,saved.getValue().completedTargets());verify(mapper,never()).scrubVersions(any(),any(),anyLong());verify(mapper,never()).completeItem(any(),any(),anyLong(),anyLong());
 }
}

