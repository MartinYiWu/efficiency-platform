package com.aiep.aihub.memory;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.api.dto.MemoryResumeRequest;
import com.aiep.identity.api.IdentityFacade;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryResumeIdempotencyTest {
 @Test void contentChangeNeverReusesOriginalOperationOrCallsAgent(){
  var scope=new MemoryScopeDTO("t","u","operations","operations","TASK_ONLY",null);
  var actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original-login");
  var policy=mock(MemoryScopePolicy.class);var bindings=mock(MemorySessionBindingService.class);var packets=mock(MemoryPacketMapper.class);var ai=mock(AiInvokeFacade.class);
  var service=new MemoryContextResumeService(policy,bindings,packets,ai);
  assertThrows(MemoryContracts.MemoryException.class,()->service.resume(actor,scope,"execution",new MemoryResumeRequest("wait",1,1,"resume","a".repeat(64),"refresh",true)));
  verify(policy).require(actor,scope,Set.of());verify(bindings).require(actor,scope);verifyNoInteractions(packets,ai);
 }
 @Test void missingOriginalExecutionCannotIssueNewAuthorizationOrDeadline(){
  var scope=new MemoryScopeDTO("t","u","operations","operations","TASK_ONLY",null);
  var actor=new IdentityFacade.Subject("t","u",Set.of(),Set.of(),Set.of(),Set.of(),List.of(),"original-login");
  var ai=mock(AiInvokeFacade.class);
  var service=new MemoryContextResumeService(mock(MemoryScopePolicy.class),mock(MemorySessionBindingService.class),mock(MemoryPacketMapper.class),ai);
  assertEquals("MEMORY_REVISION_CONFLICT",assertThrows(MemoryContracts.MemoryException.class,()->service.resume(actor,scope,"execution",new MemoryResumeRequest("wait",1,1,"same-resume-id","a".repeat(64),"paid",false))).code());
  verifyNoInteractions(ai);
 }
}
