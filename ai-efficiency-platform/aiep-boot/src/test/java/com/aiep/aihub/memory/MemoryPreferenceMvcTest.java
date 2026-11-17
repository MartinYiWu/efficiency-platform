package com.aiep.aihub.memory;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemoryContracts.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.web.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformcore.config.TraceIdFilter;
import java.util.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.mockito.Mockito.*;
class MemoryPreferenceMvcTest {
 final MemoryFacade facade=mock(MemoryFacade.class);final MemoryScopePolicy policy=mock(MemoryScopePolicy.class);final MemoryPreferenceService preferences=mock(MemoryPreferenceService.class);
 final org.springframework.test.web.servlet.MockMvc mvc=MockMvcBuilders.standaloneSetup(new MemoryController(facade,policy,preferences)).setControllerAdvice(new MemoryExceptionHandler()).addFilters(new TraceIdFilter()).build();
 final IdentityFacade.Subject actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original-login-secret-ref");
 final String body="{\"topAgent\":\"operations\",\"sessionId\":\"business-session\",\"fieldKey\":\"response.language\",\"value\":\"zh-CN\",\"expectedRevision\":0,\"idempotencyKey\":\"once\"}";
 @Test void responseUsesSafeProjectionAndBusinessSessionScope()throws Exception{
  when(policy.currentActor()).thenReturn(actor);when(facade.savePreference(eq(actor),any())).thenAnswer(i->{PreferenceCommand c=i.getArgument(1);org.junit.jupiter.api.Assertions.assertEquals("business-session",c.scope().sessionId());return new Preference("i","v",c.scope(),c.fieldKey(),c.value(),1,"ACTIVE","USER_PREFERENCE_DECISION","safe",Instant.now().plusSeconds(60));});
  mvc.perform(post("/api/aihub/memories").header("X-Trace-Id","trace").contentType("application/json").content(body)).andExpect(status().isOk()).andExpect(jsonPath("$.data.topAgent").value("operations")).andExpect(jsonPath("$.data.tenantId").doesNotExist()).andExpect(jsonPath("$.data.scope").doesNotExist()).andExpect(jsonPath("$.traceId").value("trace")).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("original-login"))));
 }
 @Test void unknownOwnerAndProposalAreRejectedWithoutCallingWriter()throws Exception{
  mvc.perform(post("/api/aihub/memories").contentType("application/json").content(body.replace("{","{\"owner\":\"other\","))).andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("MEMORY_REQUEST_INVALID"));
  mvc.perform(post("/api/aihub/memories/i/decisions").contentType("application/json").content("{\"proposalId\":\"not-built\"}")).andExpect(status().isUnprocessableEntity()).andExpect(jsonPath("$.code").value("FEATURE_DISABLED"));verifyNoInteractions(facade,preferences);
 }
 @Test void managementWithoutBusinessSessionUsesTaskOnly()throws Exception{when(policy.currentActor()).thenReturn(actor);when(facade.listPreferences(eq(actor),any(),any())).thenReturn(List.of());mvc.perform(get("/api/aihub/memories").param("topAgent","operations")).andExpect(status().isOk());var captor=org.mockito.ArgumentCaptor.forClass(MemoryScopeDTO.class);verify(facade).listPreferences(eq(actor),captor.capture(),any());org.junit.jupiter.api.Assertions.assertEquals("TASK_ONLY",captor.getValue().sessionKind());org.junit.jupiter.api.Assertions.assertNull(captor.getValue().historyKey());}
 @Test void disabledErrorsCarryTraceAndNoBody()throws Exception{when(policy.currentActor()).thenReturn(actor);when(facade.savePreference(any(),any())).thenThrow(new MemoryException("FEATURE_DISABLED"));mvc.perform(post("/api/aihub/memories").header("X-Trace-Id","error-trace").contentType("application/json").content(body)).andExpect(status().isUnprocessableEntity()).andExpect(header().string("X-Trace-Id","error-trace")).andExpect(jsonPath("$.traceId").value("error-trace")).andExpect(jsonPath("$.data").isEmpty());}
 @Test void invalidPagingAndMissingScopeFailWithoutRepositoryWork()throws Exception{mvc.perform(get("/api/aihub/memories").param("topAgent","operations").param("pageSize","101")).andExpect(status().isBadRequest());mvc.perform(get("/api/aihub/memories")).andExpect(status().isBadRequest());verifyNoInteractions(facade,preferences);}
}
