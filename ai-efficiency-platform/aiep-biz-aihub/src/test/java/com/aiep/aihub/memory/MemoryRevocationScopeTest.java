package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.memory.MemoryForgetMapper.*;
import com.aiep.identity.api.IdentityFacade;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

class MemoryRevocationScopeTest {
 final MemoryMapper memories=mock(MemoryMapper.class);final MemoryForgetMapper mapper=mock(MemoryForgetMapper.class);
 final MemoryForgetService forget=mock(MemoryForgetService.class);final PlatformTransactionManager manager=mock(PlatformTransactionManager.class);
 final MemorySourceInvalidationService service=new MemorySourceInvalidationService(memories,mapper,forget,manager);
 final IdentityFacade.Subject actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original");
 final MemoryScopeDTO scope=new MemoryScopeDTO("t","u","operations","operations","TASK_ONLY",null);
 static byte[] b(String s){return MemoryMapper.identity(s);}
 @Test void disabledProjectAndSharingNeverDeletePrivateValues(){
  assertEquals("FEATURE_DISABLED",assertThrows(MemoryException.class,()->service.principalLeftProject(actor,scope)).code());
  assertEquals("FEATURE_DISABLED",assertThrows(MemoryException.class,()->service.withdrawSharing(actor,scope)).code());
  verifyNoInteractions(memories,mapper);
 }
 @Test void sourceRevocationCannotUseAnotherOwnerOrAgent(){
  when(manager.getTransaction(any())).thenAnswer(i->new SimpleTransactionStatus());
  when(mapper.lockSource(any(),any())).thenReturn(new SourcePO(b("t"),b("source"),"USER_PREFERENCE_DECISION",b("d"),b("v"),0,1,0,null));
  when(mapper.sourceOwner(any(),any())).thenReturn(new SourceOwnerPO(b("other"),"operations","operations",b("item")),new SourceOwnerPO(b("u"),"hr","hr",b("item")));
  for(int n=0;n<2;n++)assertEquals("MEMORY_NOT_FOUND",assertThrows(MemoryException.class,()->service.invalidateOwnedSource(actor,scope,"source",1)).code());
  verify(mapper,never()).revokeSource(any());verify(mapper,never()).revokeItem(any());
 }
 @Test void successfulSourceTombstoneUpsertIsNotASingleRowCas(){
  when(manager.getTransaction(any())).thenAnswer(i->new SimpleTransactionStatus());
  when(mapper.lockSource(any(),any())).thenReturn(new SourcePO(b("t"),b("source"),"USER_PREFERENCE_DECISION",b("d"),b("v"),0,1,0,null));
  when(mapper.sourceOwner(any(),any())).thenReturn(new SourceOwnerPO(b("u"),"operations","operations",b("item")));
  when(memories.findItemForUpdate(any(),any())).thenReturn(new MemoryForgetTest().item("u","LIVE"));
  when(mapper.listSourceDependencies(any(),any())).thenReturn(List.of());when(mapper.revokeSource(any())).thenReturn(1);
  when(memories.advanceTombstone(any(),any(),any(),anyLong(),anyLong(),anyLong())).thenReturn(2);
  when(memories.insertOutbox(any(),any(),any(),any(),any(),anyLong())).thenReturn(1);
  assertEquals("REVOKED",service.invalidateOwnedSource(actor,scope,"source",1).status());
 }
}
