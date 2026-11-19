package com.aiep.aihub.memory;

import com.aiep.aihub.application.customer.*;
import com.aiep.aihub.application.operation.*;
import com.aiep.aihub.repository.customer.*;
import com.aiep.aihub.repository.customer.CustomerServicePOs.*;
import com.aiep.aihub.web.operation.OperationAssistantController;
import com.aiep.aihub.web.memory.MemoryActorResolver;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.Map;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class MemoryRefreshEventEntryTest {
    static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules();
    static final OperationActor ACTOR=new OperationActor("t","u","original-login");
    static final Instant NOW=Instant.parse("2026-11-18T00:00:00Z");
    static OperationAgentRunEvent operationWait(){return new OperationAgentRunEvent("operation-run-event/1","context_refresh_required","agent-run",2,Map.of("wait_event_id","wait-ref"));}
    static CustomerServiceRunEvent customerWait()throws Exception {
        return JSON.readValue("{\"contract_version\":\"customer-service-run-event/1\",\"run_id\":\"agent-run\",\"sequence\":2,\"event_type\":\"context_refresh_required\",\"status\":\"RUNNING\",\"occurred_at\":\"2026-11-18T00:00:00Z\",\"payload\":{\"context_wait_ref\":\"wait-ref\"}}",CustomerServiceRunEvent.class);
    }
    static RunPO customerRun(){return new RunPO("java-run","conversation","t","message","agent-run","release","RUNNING",null,1,null,null,NOW,null,NOW,NOW);}

    @Test void operationInternalWaitNeverReachesEmployeeSse()throws Exception {
        var service=mock(OperationAssistantService.class);var controller=new OperationAssistantController(service,mock(MemoryActorResolver.class));
        var emitter=mock(SseEmitter.class);var method=OperationAssistantController.class.getDeclaredMethod("sendEvent",SseEmitter.class,String.class,OperationAgentRunEvent.class,OperationActor.class);method.setAccessible(true);
        method.invoke(controller,emitter,"java-run",operationWait(),ACTOR);
        verify(service).projectEvent("java-run",operationWait(),ACTOR);
        verifyNoInteractions(emitter);
    }
    @Test void customerInternalWaitDtoAcceptsOnlyNarrowReference()throws Exception {
        var event=customerWait();assertEquals("context_refresh_required",event.eventType());
        var serialized=JSON.valueToTree(event);
        assertEquals("wait-ref",serialized.at("/payload/context_wait_ref").asText());
        assertThrows(Exception.class,()->JSON.treeToValue(((com.fasterxml.jackson.databind.node.ObjectNode)serialized).put("status","SUCCEEDED"),CustomerServiceRunEvent.class));
    }
    @Test void customerWaitAdvancesInternalCursorWithoutPublicStepOrMessage()throws Exception {
        var repository=mock(CustomerServiceMappers.class);when(repository.findRun("java-run","t")).thenReturn(customerRun());
        when(repository.advanceRun(any(),anyLong(),anyLong(),any(),any(),any(),any())).thenReturn(true);
        when(repository.findAssistantMessageByRun(any(),any())).thenReturn(new MessagePO("answer","conversation","t","ASSISTANT","","STREAMING",null,"java-run",null,NOW));
        var projector=new CustomerServiceEventProjector(repository,JSON);
        assertNull(projector.project("java-run","t",customerWait()));
        verify(repository).advanceRun("java-run",1,2,"RUNNING",null,null,null);
        verify(repository,never()).insertRunStep(any());verify(repository,never()).findAssistantMessageByRun(any(),any());
    }
    @Test void operationProjectionCommitsBeforeResumeAndUnknownResponseReusesWaitRef()throws Exception {
        var conversations=mock(com.aiep.aihub.repository.operation.OperationConversationMapper.class);
        var runs=mock(com.aiep.aihub.repository.operation.OperationRunMapper.class);
        var messages=mock(com.aiep.aihub.repository.operation.OperationMessageMapper.class);
        var artifacts=mock(com.aiep.aihub.repository.operation.OperationArtifactMapper.class);
        var actors=mock(com.aiep.aihub.application.memory.MemoryActorProvider.class);when(actors.revalidate(ACTOR)).thenReturn(ACTOR);
        var run=new com.aiep.aihub.repository.operation.OperationRunPO();run.setId("java-run");run.setConversationId("conversation");run.setTenantId("t");run.setAgentRunId("agent-run");run.setStatus("running");run.setLastEventSequence(1);
        var conversation=new com.aiep.aihub.repository.operation.OperationConversationPO();conversation.setId("conversation");conversation.setTenantId("t");conversation.setUserId("u");
        when(conversations.selectOne(any())).thenReturn(conversation);when(runs.selectOne(any())).thenReturn(run);
        when(runs.selectForUpdate("java-run","t")).thenAnswer(call->{assertTrue(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());return run;});
        var resumes=mock(com.aiep.aihub.application.memory.MemoryContextResumeService.class);var keys=new java.util.ArrayList<String>();
        when(resumes.onWaitEvent(eq("t"),eq("java-run"),eq("agent-run"),eq("wait-ref"))).thenAnswer(call->{
            assertFalse(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());keys.add(call.getArgument(3));
            if(keys.size()==1)throw new IllegalStateException("synthetic-response-unknown");return null;
        });
        var service=transactional(new OperationAssistantService(conversations,messages,runs,artifacts,mock(com.aiep.platformai.api.AiInvokeFacade.class),JSON,actors,resumes));
        var controller=new OperationAssistantController(service,mock(MemoryActorResolver.class));var emitter=mock(SseEmitter.class);
        var method=OperationAssistantController.class.getDeclaredMethod("sendEvent",SseEmitter.class,String.class,OperationAgentRunEvent.class,OperationActor.class);method.setAccessible(true);
        var failure=assertThrows(java.lang.reflect.InvocationTargetException.class,()->method.invoke(controller,emitter,"java-run",operationWait(),ACTOR));
        assertEquals("MEMORY_CONTEXT_REFRESH_FAILED",failure.getCause().getMessage());
        method.invoke(controller,emitter,"java-run",operationWait(),ACTOR);
        assertEquals(2,keys.size());assertEquals(keys.get(0),keys.get(1));assertEquals("wait-ref",keys.get(0));
        assertEquals(1,run.getLastEventSequence());verify(runs,never()).updateById(any(com.aiep.aihub.repository.operation.OperationRunPO.class));verifyNoInteractions(emitter,messages,artifacts);
        verify(actors,never()).current();
    }
    @Test void customerControllerResumesAfterCommitAndRepeatedWaitStaysPrivate()throws Exception {
        var repository=mock(CustomerServiceMappers.class);var state=new java.util.concurrent.atomic.AtomicReference<>(customerRun());
        when(repository.findRun("java-run","t")).thenAnswer(call->state.get());
        when(repository.findConversation("conversation","t","u")).thenReturn(new ConversationPO("conversation","t","u","synthetic","ACTIVE",NOW,NOW,NOW));
        when(repository.advanceRun("java-run",1,2,"RUNNING",null,null,null)).thenAnswer(call->{
            assertTrue(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive());
            state.set(new RunPO("java-run","conversation","t","message","agent-run","release","RUNNING",null,2,null,null,NOW,null,NOW,NOW));return true;
        });
        var actors=mock(MemoryActorResolver.class);when(actors.current()).thenReturn(ACTOR);when(actors.revalidate(ACTOR)).thenReturn(ACTOR);
        var resumes=mock(com.aiep.aihub.application.memory.MemoryContextResumeService.class);var done=new java.util.concurrent.CountDownLatch(2);var failures=new java.util.concurrent.ConcurrentLinkedQueue<String>();var keys=new java.util.concurrent.CopyOnWriteArrayList<String>();
        when(resumes.onWaitEvent(eq("t"),eq("java-run"),eq("agent-run"),eq("wait-ref"))).thenAnswer(call->{
            if(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive())failures.add("resume-in-transaction");
            keys.add(call.getArgument(3));done.countDown();return null;
        });
        var projector=transactional(new CustomerServiceEventProjector(repository,JSON,actors,resumes));
        var service=mock(CustomerServiceApplicationService.class);when(service.getRun("t","u","java-run")).thenAnswer(call->state.get());
        var wait=customerWait();when(service.stream("t","u","java-run",0)).thenReturn(reactor.core.publisher.Flux.just(wait,wait));
        new com.aiep.aihub.web.customer.CustomerServiceController(service,projector,actors).events("java-run",null,0);
        assertTrue(done.await(3,java.util.concurrent.TimeUnit.SECONDS));assertTrue(failures.isEmpty(),failures.toString());
        assertEquals(2,keys.size());assertEquals(keys.get(0),keys.get(1));assertEquals(2,state.get().lastEventSequence());
        verify(repository,never()).insertRunStep(any());verify(repository,never()).findAssistantMessageByRun(any(),any());verify(repository,never()).completeAssistantMessage(any(),any(),any(),any());
    }
    @Test void staleCustomerProjectionCannotResumeBeforeItsCursorCommits()throws Exception {
        var repository=mock(CustomerServiceMappers.class);when(repository.findRun("java-run","t")).thenReturn(customerRun());
        when(repository.findConversation("conversation","t","u")).thenReturn(new ConversationPO("conversation","t","u","synthetic","ACTIVE",NOW,NOW,NOW));
        var actors=mock(com.aiep.aihub.application.memory.MemoryActorProvider.class);when(actors.revalidate(ACTOR)).thenReturn(ACTOR);
        var resumes=mock(com.aiep.aihub.application.memory.MemoryContextResumeService.class);
        var projector=new CustomerServiceEventProjector(repository,JSON,actors,resumes);
        assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->projector.onMemoryWait("java-run",customerWait(),ACTOR));
        verifyNoInteractions(resumes);
    }
    @Test void terminalCustomerReplayCannotExposeInternalWaitReferences()throws Exception {
        var repository=mock(CustomerServiceMappers.class);
        when(repository.findRun("java-run","t")).thenReturn(new RunPO("java-run","conversation","t","message","agent-run","release","SUCCEEDED",null,3,null,null,NOW,NOW,NOW,NOW));
        when(repository.listRunSteps("java-run")).thenReturn(List.of(new RunStepPO("step","java-run",2,"context_refresh_required","RUNNING",null,"{\"_event_type\":\"context_refresh_required\",\"context_wait_ref\":\"wait-ref\"}",NOW,NOW)));
        assertTrue(new CustomerServiceEventProjector(repository,JSON).replay("java-run","t",0).isEmpty());
    }
    @Test void operationForeignRuntimeOrTenantNeverCallsResume() {
        var conversations=mock(com.aiep.aihub.repository.operation.OperationConversationMapper.class);var runs=mock(com.aiep.aihub.repository.operation.OperationRunMapper.class);
        var conversation=new com.aiep.aihub.repository.operation.OperationConversationPO();conversation.setId("conversation");conversation.setTenantId("t");conversation.setUserId("u");when(conversations.selectOne(any())).thenReturn(conversation);
        var run=new com.aiep.aihub.repository.operation.OperationRunPO();run.setId("java-run");run.setConversationId("conversation");run.setTenantId("t");run.setAgentRunId("different-runtime");run.setStatus("running");when(runs.selectOne(any())).thenReturn(run);
        var actors=mock(com.aiep.aihub.application.memory.MemoryActorProvider.class);when(actors.revalidate(ACTOR)).thenReturn(ACTOR);var resumes=mock(com.aiep.aihub.application.memory.MemoryContextResumeService.class);
        var service=new OperationAssistantService(conversations,mock(com.aiep.aihub.repository.operation.OperationMessageMapper.class),runs,mock(com.aiep.aihub.repository.operation.OperationArtifactMapper.class),mock(com.aiep.platformai.api.AiInvokeFacade.class),JSON,actors,resumes);
        assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->service.onMemoryWait("java-run",operationWait(),ACTOR));
        run.setAgentRunId("agent-run");run.setTenantId("foreign-tenant");
        assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->service.onMemoryWait("java-run",operationWait(),ACTOR));
        verifyNoInteractions(resumes);verify(actors,never()).current();
    }
    @Test void customerForeignRuntimeOrTenantNeverCallsResume()throws Exception {
        var repository=mock(CustomerServiceMappers.class);var actors=mock(com.aiep.aihub.application.memory.MemoryActorProvider.class);when(actors.revalidate(ACTOR)).thenReturn(ACTOR);
        var resumes=mock(com.aiep.aihub.application.memory.MemoryContextResumeService.class);var projector=new CustomerServiceEventProjector(repository,JSON,actors,resumes);
        when(repository.findRun("java-run","t")).thenReturn(new RunPO("java-run","conversation","t","message","different-runtime","release","RUNNING",null,2,null,null,NOW,null,NOW,NOW));
        assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->projector.onMemoryWait("java-run",customerWait(),ACTOR));
        when(repository.findRun("java-run","t")).thenReturn(new RunPO("java-run","conversation","foreign-tenant","message","agent-run","release","RUNNING",null,2,null,null,NOW,null,NOW,NOW));
        assertThrows(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class,()->projector.onMemoryWait("java-run",customerWait(),ACTOR));
        verifyNoInteractions(resumes);
    }
    @Test void customerWaitRejectsContentAndOldPayloadWireStaysCompatible()throws Exception {
        var event=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.valueToTree(customerWait());
        ((com.fasterxml.jackson.databind.node.ObjectNode)event.get("payload")).put("public_summary","synthetic-content");
        assertThrows(Exception.class,()->JSON.treeToValue(event,CustomerServiceRunEvent.class));
        var old=new CustomerServiceRunEvent.Payload(null,null,null,null,null,null,null,null,null,null,null);
        assertFalse(JSON.valueToTree(old).has("context_wait_ref"));
    }
    @Test void customerInternalWaitPreservesExistingBusinessFacts()throws Exception {
        var repository=mock(CustomerServiceMappers.class);
        when(repository.findRun("java-run","t")).thenReturn(new RunPO("java-run","conversation","t","message","agent-run","release","RUNNING","GENERAL",1,"SYNTHETIC_PRIOR","synthetic-safe-message",NOW,null,NOW,NOW));
        new CustomerServiceEventProjector(repository,JSON).project("java-run","t",customerWait());
        verify(repository).advanceRun("java-run",1,2,"RUNNING","GENERAL","SYNTHETIC_PRIOR","synthetic-safe-message");
        verify(repository,never()).insertRunStep(any());
    }
    @SuppressWarnings("unchecked")
    static <T> T transactional(T target) {
        var manager=new org.springframework.transaction.support.AbstractPlatformTransactionManager() {
            protected Object doGetTransaction(){return new Object();}
            protected void doBegin(Object tx,org.springframework.transaction.TransactionDefinition definition){}
            protected void doCommit(org.springframework.transaction.support.DefaultTransactionStatus status){}
            protected void doRollback(org.springframework.transaction.support.DefaultTransactionStatus status){}
        };
        var proxy=new org.springframework.aop.framework.ProxyFactory(target);proxy.setProxyTargetClass(true);
        proxy.addAdvice(new org.springframework.transaction.interceptor.TransactionInterceptor(manager,new org.springframework.transaction.annotation.AnnotationTransactionAttributeSource()));
        return (T)proxy.getProxy();
    }
}
