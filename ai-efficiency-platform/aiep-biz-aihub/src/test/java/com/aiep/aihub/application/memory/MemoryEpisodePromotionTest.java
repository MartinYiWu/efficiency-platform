package com.aiep.aihub.application.memory;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.aiep.aihub.api.memory.MemoryContracts.MemoryException;
import com.aiep.aihub.api.memory.MemoryEpisodeContracts.*;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.management.*;
import com.aiep.aihub.repository.management.AiManagementMappers;
import com.aiep.aihub.repository.management.AiManagementPOs.PromptDefinitionPO;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper;
import com.aiep.aihub.repository.memory.MemoryEpisodeMapper.PromotionPO;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.MemoryContextPacket.Dependency;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;

class MemoryEpisodePromotionTest {
    final MemoryScopeDTO scope=new MemoryScopeDTO("tenant","owner","operations","operations","CONVERSATION","session");
    static byte[] b(String value){return MemoryMapper.identity(value);}
    Content content(String category){return new Content(category,"合成适用场景",List.of("有明确条件"),List.of("人工步骤"),"用户偏好反馈",null,null,null,List.of("source"),"v1",List.of("无依据时禁用"));}
    @Test void likesOrFreeTextCannotBecomeMeasuredResultsOrHrGroupFacts() {
        var dependency=List.of(new Dependency("CURRENT_USER_MESSAGE","source","hash",0,1,0));
        assertThrows(MemoryException.class,()->content("MEASURED_RESULT"));
        var measured=new Content("MEASURED_RESULT","场景",List.of(),List.of("动作"),"结果",100L,Instant.EPOCH,Instant.EPOCH.plusSeconds(10),List.of("source"),"v1",List.of());
        assertEquals("MEMORY_EPISODE_MEASUREMENT_AUTHORITY_REQUIRED",assertThrows(MemoryException.class,()->MemoryEpisodeService.validateEvidence(measured,scope,dependency)).code());
        var hr=new MemoryScopeDTO("tenant","owner","hr","hr","TASK_ONLY",null);
        assertEquals("MEMORY_EPISODE_HR_SOURCE_DENIED",assertThrows(MemoryException.class,()->MemoryEpisodeService.validateEvidence(content("USER_PREFERENCE"),hr,dependency)).code());
        assertDoesNotThrow(()->MemoryEpisodeService.validateEvidence(content("USER_PREFERENCE"),scope,dependency));
    }
    @Test void fixedRegressionBindsActualCandidateSuiteCountsAndReport() throws Exception {
        var policy=new ObjectMapper().readTree("{\"suiteId\":\"fixed-memory\",\"suiteVersion\":\"1\",\"minCases\":3}");
        var good=new RegressionCommand(0,"fixed-memory","1","c".repeat(64),"a".repeat(64),3,3,"request");
        assertDoesNotThrow(()->MemoryPromotionService.validateRegression(policy,"c".repeat(64),good));
        assertThrows(MemoryException.class,()->MemoryPromotionService.validateRegression(policy,"d".repeat(64),good));
        assertThrows(MemoryException.class,()->MemoryPromotionService.validateRegression(policy,"c".repeat(64),new RegressionCommand(0,"fixed-memory","2","c".repeat(64),"a".repeat(64),3,3,"request")));
        assertThrows(MemoryException.class,()->MemoryPromotionService.validateRegression(policy,"c".repeat(64),new RegressionCommand(0,"fixed-memory","1","c".repeat(64),"a".repeat(64),3,2,"request")));
    }
    @Test void revokedSourceAndLegacyRouteCannotPublishMemoryCandidate() {
        var mapper=mock(MemoryEpisodeMapper.class);var identity=mock(IdentityFacade.class);var guard=new MemoryPromotionAssetGuard(mapper,identity);
        var actor=new IdentityFacade.Subject("tenant","publisher",Set.of(),Set.of("memory:promotion:publish"),Set.of(),Set.of(),List.of(),"login");
        when(identity.refresh("tenant","publisher","login")).thenReturn(Optional.of(actor));
        var row=new PromotionPO(b("tenant"),b("promotion"),b("episode"),b("creator"),"PROMPT","definition","version","c".repeat(64),"REGRESSION_PASSED",1,b("request"),"f".repeat(64),"suite","1","a".repeat(64),3,3,b("reviewer"),null);
        when(mapper.findAssetPromotion("PROMPT","version")).thenReturn(row);
        assertEquals("MEMORY_PROMOTION_APPROVAL_ROUTE_REQUIRED",assertThrows(MemoryException.class,()->guard.transition("PROMPT","version","PUBLISHED",null)).code());
        assertEquals("MEMORY_PROMOTION_SOURCE_REVOKED",assertThrows(MemoryException.class,()->guard.transition("PROMPT","version","PUBLISHED",actor)).code());
        when(mapper.assetSourcesCurrent(any(),any())).thenReturn(1);
        assertDoesNotThrow(()->guard.transition("PROMPT","version","PUBLISHED",actor));
    }
    @Test void existingPromptDraftPathPreservesActualActor() {
        var repository=mock(AiManagementMappers.class);var now=LocalDateTime.now();
        when(repository.findPromptDefinition("definition")).thenReturn(new PromptDefinitionPO("definition","prompt","SHARED",null,"name","description","stage","ACTIVE","owner",now,"owner",now));
        var draft=new AiPromptManagementService(repository).createVersion("definition","1.1.0","memory-episode:episode 人工候选","actual-user");
        assertEquals("DRAFT",draft.status());assertEquals("actual-user",draft.createdBy());
        verify(repository).insertPromptVersion(eq(draft));verify(repository,never()).updatePromptVersion(any());
    }
}
