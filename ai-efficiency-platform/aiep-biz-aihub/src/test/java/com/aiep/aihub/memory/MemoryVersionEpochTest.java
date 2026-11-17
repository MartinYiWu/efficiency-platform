package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.MemoryMapper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryVersionEpochTest {
    @Test void correctionAfterReauthorizationInheritsItemEpochsWithoutResettingNewSourceEpoch() throws Exception {
        var mapper = mock(MemoryMapper.class);
        when(mapper.findPolicyVersion(any(),any(),any())).thenReturn(new MemoryMapper.PolicyPO("p".getBytes(),"v".getBytes(),MemoryArtifactPolicyTest.withArtifacts("{}"),null,"memory-policy/1"));
        when(mapper.clearPreferenceCurrent(any(),any(),anyLong(),any())).thenReturn(1);
        when(mapper.retirePreferenceVersion(any(),any(),any())).thenReturn(1);
        when(mapper.insertPreferenceVersion(any())).thenReturn(1);
        when(mapper.insertPreferenceSource(any(),any(),any(),any(),any())).thenReturn(1);
        when(mapper.insertPreferenceDependency(any(),any(),any(),any())).thenReturn(1);
        when(mapper.compareAndSetCurrent(any(),any(),anyLong(),any(),any())).thenReturn(1);
        var item = new MemoryMapper.MemoryItemPO("t".getBytes(),"i".getBytes(),"USER","u".getBytes(),"u".getBytes(),"operations","operations",
            "USER_PRIVATE",MemoryMapper.privateScope("u","operations"),"assistant_response","response.language","LIVE",5,"old".getBytes(),2,3,1);
        var version = new MemoryVersionService(mapper, MemoryPreferenceTest.codec()).replace(item,"new".getBytes(),"decision".getBytes(),"en-US",
            new MemoryPolicyService.Published("p".getBytes(),"v".getBytes(),100));
        assertEquals(2L, version.getClass().getMethod("grantEpoch").invoke(version));
        assertEquals(3L, version.getClass().getMethod("sourceEpoch").invoke(version));
        assertEquals(1L, version.getClass().getMethod("deletionEpoch").invoke(version));
        verify(mapper).insertPreferenceSource(any(),any(),any(),any(),any());
    }
}
