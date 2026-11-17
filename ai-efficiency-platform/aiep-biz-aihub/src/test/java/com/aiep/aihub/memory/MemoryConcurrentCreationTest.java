package com.aiep.aihub.memory;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;
/** 离线仅验证唯一冲突事务边界；实际并发由真实IT验证。 */
class MemoryConcurrentCreationTest {
 @Test void uniqueLoserRollsBackBeforeOneWinnerReadAndNeverRetriesDeadlock(){var f=new MemoryPreferenceTest();f.enabled();var saved=f.service.save(f.actor,f.command("zh-CN",0,"one"));clearInvocations(f.mapper,f.manager);
  when(f.mapper.findPreferenceItem(any(),any(),any(),any())).thenReturn(null,f.item);doThrow(new DuplicateKeyException("unique")).when(f.mapper).insertItem(any());
  assertEquals(saved.id(),f.service.save(f.actor,f.command("zh-CN",0,"two")).id());var order=inOrder(f.manager,f.mapper);order.verify(f.mapper).insertItem(any());order.verify(f.manager).rollback(any());order.verify(f.mapper).findPreferenceItem(any(),any(),any(),any());verify(f.mapper,times(1)).insertItem(any());
  when(f.mapper.findPreferenceItem(any(),any(),any(),any())).thenThrow(new org.springframework.dao.CannotAcquireLockException("deadlock"));assertThrows(org.springframework.dao.CannotAcquireLockException.class,()->f.service.save(f.actor,f.command("zh-CN",0,"three")));
 }
}
