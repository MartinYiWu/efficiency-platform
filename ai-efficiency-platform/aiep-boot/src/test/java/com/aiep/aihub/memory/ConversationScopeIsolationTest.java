package com.aiep.aihub.memory;
import com.aiep.aihub.api.memory.MemoryScopeDTO;
import com.aiep.aihub.application.memory.ConversationScopeResolver;
import com.aiep.aihub.application.operation.OperationActor;
import com.aiep.aihub.web.memory.MemoryActorResolver;
import com.aiep.identity.api.IdentityFacade;
import org.springframework.mock.web.MockHttpServletRequest;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class ConversationScopeIsolationTest {
 private final ConversationScopeResolver scopes = new ConversationScopeResolver();
 @Test void everyHistoryDimensionIsExactAndTaskOnlyHasNoHistory() {
  var base = scopes.conversation(new OperationActor("t1","u1"),"operations","s1","t1","u1","operations");
  Set<List<String>> keys = new HashSet<>(); keys.add(base.historyKey());
  keys.add(scopes.conversation(new OperationActor("t2","u1"),"operations","s1","t2","u1","operations").historyKey());
  keys.add(scopes.conversation(new OperationActor("t1","u2"),"operations","s1","t1","u2","operations").historyKey());
  keys.add(scopes.conversation(new OperationActor("t1","u1"),"customer-service","s1","t1","u1","customer-service").historyKey());
  keys.add(scopes.conversation(new OperationActor("t1","u1"),"operations","s2","t1","u1","operations").historyKey());
  assertEquals(5,keys.size());
  var task = scopes.taskOnly(new OperationActor("t1","u1"),"hr");
  assertNull(task.sessionId()); assertNull(task.historyKey());
 }
 @Test void forgedOwnershipAndCrossAgentSessionAreRejected() {
  var actor = new OperationActor("t1","u1");
  assertThrows(IllegalArgumentException.class,()->scopes.conversation(actor,"operations","s1","t2","u1","operations"));
  assertThrows(IllegalArgumentException.class,()->scopes.conversation(actor,"operations","s1","t1","u2","operations"));
  assertThrows(IllegalArgumentException.class,()->scopes.conversation(actor,"customer-service","s1","t1","u1","operations"));
  assertThrows(IllegalArgumentException.class,()->new MemoryScopeDTO("t","u","operations","hr","CONVERSATION","s"));
  assertThrows(IllegalArgumentException.class,()->new MemoryScopeDTO("t","u","hr","hr","TASK_ONLY","null"));
 }
 @Test void httpIdentityFailsClosedAndIgnoresSelfReportedHeaders() {
  var identity=mock(IdentityFacade.class);
  var resolver=new MemoryActorResolver(identity,false,"","");
  var request=new MockHttpServletRequest(); request.addHeader("X-Tenant-Id","forged");request.addHeader("X-User-Id","forged");
  assertThrows(RuntimeException.class,()->resolver.resolve(request));
  request.addHeader("Authorization","Bearer valid");
  when(identity.authenticate("valid")).thenReturn(Optional.of(subject("t1","u1","original")));
  assertEquals(new OperationActor("t1","u1","original"),resolver.resolve(request));
  verify(identity).authenticate("valid");
 }
 @Test void expiredOriginalSessionNeverBorrowsOtherLoginOrFallsBackToDevelopment() {
  var identity=mock(IdentityFacade.class);
  var resolver=new MemoryActorResolver(identity,true,"dev","1");
  var actor=new OperationActor("t1","u1","original");
  when(identity.refresh("t1","u1","original")).thenReturn(Optional.empty());
  assertThrows(RuntimeException.class,()->resolver.revalidate(actor));
  verify(identity,never()).refresh("t1","u1");
  var request=new MockHttpServletRequest();request.setRemoteAddr("127.0.0.1");request.addHeader("Authorization","Bearer expired");
  when(identity.authenticate("expired")).thenReturn(Optional.empty());
  assertThrows(RuntimeException.class,()->resolver.resolve(request));
 }
 @Test void idempotencyScopeConflictIsHttp409() {
  var handler = new com.aiep.aihub.web.operation.OperationAssistantExceptionHandler();
  var response = handler.handleBusiness(new com.aiep.aihub.application.operation.OperationAssistantException("IDEMPOTENCY_SCOPE_CONFLICT", "scope conflict"));
  assertEquals(409, response.getStatusCode().value());
 }
 @Test void customerIdempotencyCannotReturnAnotherSessionRun() {
  var repository=mock(com.aiep.aihub.repository.customer.CustomerServiceMappers.class);
  var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);
  var service=new com.aiep.aihub.application.customer.CustomerServiceApplicationService(repository,
   mock(com.aiep.aihub.repository.management.AiManagementMappers.class),mock(com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.class),ai);
  when(repository.findConversation("current","t","u")).thenReturn(new com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO("current","t","u","title","ACTIVE",null,null,null));
  when(repository.findMessageByClientRequest("t","same")).thenReturn(new com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO("m","other","t","USER","x","COMPLETED",null,"other-run","same",null));
  assertThrows(IllegalStateException.class,()->service.submit("t","u","current","customer-service-message/1","message","same"));
  verifyNoInteractions(ai);verify(repository,never()).findRunByUserMessage(any(),any());
 }
 @Test void concurrentCustomerIdempotencyCannotReturnOtherScopePendingRun() {
  var repository=mock(com.aiep.aihub.repository.customer.CustomerServiceMappers.class);
  var management=mock(com.aiep.aihub.repository.management.AiManagementMappers.class);
  var pending=mock(com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.class);
  var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);
  var service=new com.aiep.aihub.application.customer.CustomerServiceApplicationService(repository,management,pending,ai);
  when(repository.findConversation("current","t","u")).thenReturn(new com.aiep.aihub.repository.customer.CustomerServicePOs.ConversationPO("current","t","u","title","ACTIVE",null,null,null));
  when(management.findAgentByKey("customer-service")).thenReturn(new com.aiep.aihub.repository.management.AiManagementPOs.AgentDefinitionPO("a","customer-service","title","","CUSTOMER_SERVICE","ACTIVE","u",null,"u",null));
  when(management.findActiveRelease("a","dev")).thenReturn(new com.aiep.aihub.repository.management.AiReleasePO("release","a","v","dev","ACTIVE","snapshot","u",null,null,null));
  when(repository.listCompletedHistory("current","t",12)).thenReturn(List.of());
  var other=new com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO("other-run","other-session","t","m","agent","release","PENDING",null,0,null,null,null,null,null,null);
  when(pending.create("current","t","message","same","release")).thenReturn(new com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.Pending(other,null,null,false));
  assertThrows(IllegalStateException.class,()->service.submit("t","u","current","customer-service-message/1","message","same"));
  verifyNoInteractions(ai);
 }
 @Test void customerRunStreamCancelCitationAndFeedbackRequireSameUser() {
  var repository=mock(com.aiep.aihub.repository.customer.CustomerServiceMappers.class);
  var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);
  var service=new com.aiep.aihub.application.customer.CustomerServiceApplicationService(repository,
   mock(com.aiep.aihub.repository.management.AiManagementMappers.class),mock(com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.class),ai);
  var run=new com.aiep.aihub.repository.customer.CustomerServicePOs.RunPO("r","private-session","t","m","agent-r","release","RUNNING",null,0,null,null,null,null,null,null);
  when(repository.findRun("r","t")).thenReturn(run);
  var citation=new com.aiep.aihub.repository.customer.CustomerServicePOs.CitationPO("c","r","m",1,"kb","d","v","idx","chunk","title",1,null,null,"quote","hash",null);
  when(repository.findCitation("c","t")).thenReturn(citation);
  assertThrows(IllegalArgumentException.class,()->service.getRun("t","other-user","r"));
  assertThrows(IllegalArgumentException.class,()->service.stream("t","other-user","r",0));
  assertThrows(IllegalArgumentException.class,()->service.cancel("t","other-user","r"));
  assertThrows(IllegalArgumentException.class,()->service.citation("t","other-user","c"));
  var message=new com.aiep.aihub.repository.customer.CustomerServicePOs.MessagePO("m","private-session","t","ASSISTANT","answer","COMPLETED",null,"r",null,null);
  when(repository.findMessage("m","t")).thenReturn(message);
  assertThrows(IllegalArgumentException.class,()->service.feedback("t","other-user","m","UP",null,null));
  verify(repository,never()).upsertFeedback(any());
  verifyNoInteractions(ai);
 }
 @Test void operationRunEventsProjectionCancelAndArtifactRejectAnotherUser() {
  var conversations=mock(com.aiep.aihub.repository.operation.OperationConversationMapper.class);
  var runs=mock(com.aiep.aihub.repository.operation.OperationRunMapper.class);
  var artifacts=mock(com.aiep.aihub.repository.operation.OperationArtifactMapper.class);
  var ai=mock(com.aiep.platformai.api.AiInvokeFacade.class);
  var actor=new OperationActor("t","other-user","original");
  var actors=new com.aiep.aihub.application.memory.MemoryActorProvider() {
   public OperationActor current(){return actor;}
   public OperationActor revalidate(OperationActor captured){assertEquals(actor,captured);return captured;}
  };
  var service=new com.aiep.aihub.application.operation.OperationAssistantService(conversations,
   mock(com.aiep.aihub.repository.operation.OperationMessageMapper.class),runs,artifacts,ai,new com.fasterxml.jackson.databind.ObjectMapper(),actors);
  var run=new com.aiep.aihub.repository.operation.OperationRunPO();run.setId("r");run.setTenantId("t");run.setConversationId("private-session");run.setAgentRunId("agent-r");
  when(runs.selectOne(any())).thenReturn(run);when(runs.selectForUpdate("r","t")).thenReturn(run);
  var artifact=new com.aiep.aihub.repository.operation.OperationArtifactPO();artifact.setId("a");artifact.setTenantId("t");artifact.setConversationId("private-session");
  when(artifacts.selectOne(any())).thenReturn(artifact);
  var event=new com.aiep.platformai.api.dto.OperationAgentRunEvent("operation-run-event/1","run_started","agent-r",1,Map.of());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.getRun("r")).getCode());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.streamRunEvents("r",0)).getCode());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.cancelRun("r")).getCode());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.projectEvent("r",event,actor)).getCode());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.failEventProjection("r",event,new Exception(),actor)).getCode());
  assertEquals("CONVERSATION_NOT_FOUND",assertThrows(com.aiep.aihub.application.operation.OperationAssistantException.class,()->service.getArtifact("a")).getCode());
  verifyNoInteractions(ai);verify(runs,never()).updateById(any(com.aiep.aihub.repository.operation.OperationRunPO.class));
 }
 @Test void operationOldConstructorHasNoProductionDevelopmentFallback() {
  var mapper=mock(com.aiep.aihub.repository.operation.OperationConversationMapper.class);
  var service=new com.aiep.aihub.application.operation.OperationAssistantService(mapper,
   mock(com.aiep.aihub.repository.operation.OperationMessageMapper.class),mock(com.aiep.aihub.repository.operation.OperationRunMapper.class),
   mock(com.aiep.aihub.repository.operation.OperationArtifactMapper.class),mock(com.aiep.platformai.api.AiInvokeFacade.class),new com.fasterxml.jackson.databind.ObjectMapper());
  assertThrows(IllegalStateException.class,()->service.createConversation("title"));verifyNoInteractions(mapper);
 }
 @Test void operationHttpUsesAuthenticatedIdentityAndRejectsMissingCredential() throws Exception {
  var identity=mock(IdentityFacade.class);
  when(identity.authenticate("valid")).thenReturn(Optional.of(subject("real-tenant","real-user","original")));
  var resolver=new MemoryActorResolver(identity,false,"","");
  var mapper=mock(com.aiep.aihub.repository.operation.OperationConversationMapper.class);
  var service=new com.aiep.aihub.application.operation.OperationAssistantService(mapper,
   mock(com.aiep.aihub.repository.operation.OperationMessageMapper.class),mock(com.aiep.aihub.repository.operation.OperationRunMapper.class),
   mock(com.aiep.aihub.repository.operation.OperationArtifactMapper.class),mock(com.aiep.platformai.api.AiInvokeFacade.class),new com.fasterxml.jackson.databind.ObjectMapper(),resolver);
  var mvc=org.springframework.test.web.servlet.setup.MockMvcBuilders.standaloneSetup(new com.aiep.aihub.web.operation.OperationAssistantController(service,resolver)).build();
  mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/operations/conversations")
   .contentType("application/json").content("{\"title\":\"hello\"}")).andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isUnauthorized());
  mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post("/api/operations/conversations")
   .header("Authorization","Bearer valid").header("X-Tenant-Id","forged").header("X-User-Id","forged")
   .contentType("application/json").content("{\"title\":\"hello\",\"tenant_id\":\"forged\",\"user_id\":\"forged\",\"top_level_agent_id\":\"hr\"}"))
   .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.status().isOk());
  var captor=org.mockito.ArgumentCaptor.forClass(com.aiep.aihub.repository.operation.OperationConversationPO.class);
  verify(mapper).insert(captor.capture());assertEquals("real-tenant",captor.getValue().getTenantId());assertEquals("real-user",captor.getValue().getUserId());
 }
 private static IdentityFacade.Subject subject(String t,String u,String ref) {
  return new IdentityFacade.Subject(t,u,Set.of(),Set.of(),Set.of(),Set.of(),List.of(),ref);
 }
}
