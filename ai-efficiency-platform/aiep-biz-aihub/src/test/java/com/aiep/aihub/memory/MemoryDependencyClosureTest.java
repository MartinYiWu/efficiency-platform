package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.MemoryDependencyService;
import com.aiep.aihub.application.memory.MemoryHistoryProjection;
import com.aiep.aihub.repository.memory.MemoryPacketMapper;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryDependencyClosureTest {
    final MemoryPacketMapper mapper = mock(MemoryPacketMapper.class);
    final Dependency a = new Dependency("USER_PREFERENCE_DECISION", "A", "1", 0, 1, 0);
    final Dependency b = new Dependency("USER_PREFERENCE_DECISION", "B", "2", 0, 1, 0);
    final Clock clock = Clock.fixed(Instant.ofEpochSecond(100), ZoneOffset.UTC);
    final MemoryScopeDTO scope = new MemoryScopeDTO("tenant", "user", "operations", "operations", "CONVERSATION", "s1");

    void live(Dependency dependency) {
        when(mapper.insertDependency(any(), any(), any(), any(), any(), any(), anyLong(), anyLong(), anyLong())).thenReturn(1);
        when(mapper.findSource(eq("tenant".getBytes()), eq(dependency.sourceId().getBytes())))
                .thenReturn(new MemoryPacketMapper.SourceState(dependency.sourceType(), dependency.sourceId().getBytes(),
                        dependency.sourceVersion().getBytes(), 0, 1, 0, Instant.ofEpochSecond(200), false));
    }

    @Test void displayOnlyBStillPersistsAAndBAndRevocationExcludesDerivedHistory() {
        live(a); live(b);
        var service = new MemoryDependencyService(mapper, clock);
        var closure = service.record(scope, "MESSAGE", "R", "1", "execution",
                List.of(a, b), List.of(List.of(a), List.of(b)), List.of(b));
        assertEquals(List.of(a, b), closure);
        verify(mapper).insertDependency(any(), eq("A".getBytes()), eq("MESSAGE"), eq("R".getBytes()),
                eq("1".getBytes()), eq("execution".getBytes()), eq(0L), eq(1L), eq(0L));
        when(mapper.findDependencies(any(), eq("MESSAGE"), any(), any())).thenReturn(closure);
        var history = new MemoryHistoryProjection(service);
        var message = new MemoryHistoryProjection.Message(scope, "R", "1", "assistant", "answer");
        assertEquals(List.of(message), history.select(scope, List.of(message)));
        service.record(scope, "SUMMARY", "S", "1", "execution", closure, List.of(closure), List.of(b));
        when(mapper.findSource(any(), eq("A".getBytes())))
                .thenReturn(new MemoryPacketMapper.SourceState(a.sourceType(), "A".getBytes(), "1".getBytes(),
                        0, 2, 1, Instant.ofEpochSecond(200), false));
        assertTrue(history.select(scope, List.of(message)).isEmpty());
        assertThrows(RuntimeException.class, () -> service.requireCurrent(scope, closure));
    }

    @Test void unknownHistoryAndOtherSessionsNeverEnterEnhancedPrompt() {
        var service = new MemoryDependencyService(mapper, clock);
        var history = new MemoryHistoryProjection(service);
        when(mapper.findDependencies(any(), any(), any(), any())).thenReturn(List.of());
        var unknown = new MemoryHistoryProjection.Message(scope, "legacy", "1", "assistant", "legacy body");
        assertTrue(history.select(scope, List.of(unknown)).isEmpty());
        var other = new MemoryScopeDTO("tenant", "other", "operations", "operations", "CONVERSATION", "s1");
        assertTrue(history.select(other, List.of(unknown)).isEmpty());
        verify(mapper, times(1)).findDependencies(any(), any(), any(), any());
    }

    @Test void undeclaredActualDependencyIsRejectedBeforeAnyWrite() {
        live(a); live(b);
        var service = new MemoryDependencyService(mapper, clock);
        assertThrows(RuntimeException.class, () -> service.record(scope, "MESSAGE", "R", "1", "execution",
                List.of(b), List.of(List.of(a, b)), List.of(b)));
        verify(mapper, never()).insertDependency(any(), any(), any(), any(), any(), any(), anyLong(), anyLong(), anyLong());
    }
}
