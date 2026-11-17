package com.aiep.aihub.memory;

import com.aiep.aihub.application.customer.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.customer.*;
import com.aiep.aihub.repository.customer.CustomerServicePOs.*;
import com.aiep.aihub.repository.management.*;
import com.aiep.platformai.api.*;
import com.aiep.platformai.api.dto.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class MemoryHistoryMappingTest {
    final CustomerServiceMappers repository=mock(CustomerServiceMappers.class);
    final AiManagementMappers management=mock(AiManagementMappers.class);
    final CustomerServicePendingRunCreator creator=mock(CustomerServicePendingRunCreator.class);
    final AiInvokeFacade ai=mock(AiInvokeFacade.class);
    final MemoryPacketService packets=mock(MemoryPacketService.class);
    final MemoryDependencyService dependencies=mock(MemoryDependencyService.class);
    final CustomerServiceApplicationService service=new CustomerServiceApplicationService(repository,management,creator,ai);
    final MemoryContextPacket.Dependency a=new MemoryContextPacket.Dependency("CURRENT_USER_MESSAGE","a","v",0,1,0);
    final MemoryContextPacket.Dependency b=new MemoryContextPacket.Dependency("CURRENT_USER_MESSAGE","b","v",0,1,0);
    final Instant now=Instant.now();
    MemoryHistoryMappingTest(){
        ReflectionTestUtils.setField(service,"memoryPackets",packets);
        ReflectionTestUtils.setField(service,"memoryHistory",new MemoryHistoryProjection(dependencies));
        ReflectionTestUtils.setField(service,"memoryDependencies",dependencies);
        when(packets.enabled()).thenReturn(true);
        when(packets.issueMessage(any(),any(),any(),any(),any())).thenReturn(MemoryContextEnvelope.disabled());
        when(repository.findConversation("s","t","u")).thenReturn(new ConversationPO("s","t","u","title","ACTIVE",now,now,now));
        when(management.findAgentByKey(any())).thenReturn(new AiManagementPOs.AgentDefinitionPO("agent","customer-service","name",null,"type","ACTIVE","test",null,"test",null));
        when(management.findActiveRelease(any(),any())).thenReturn(new AiReleasePO("release","agent","v","dev","ACTIVE",null,"test",null,null,null));
        var user=message("current","USER","current input");
        var answer=message("answer","ASSISTANT","");
        var run=new RunPO("run","s","t","current",null,"release","PENDING",null,0,null,null,null,null,now,now);
        when(creator.create(any(),any(),any(),any(),any())).thenReturn(new CustomerServicePendingRunCreator.Pending(run,user,answer,true));
        when(ai.submitCustomerServiceMessage(any(),any())).thenReturn(new CustomerServiceRunView("customer-service-run-view/1","python","request",CustomerServiceRunView.Status.PENDING));
    }
    MessagePO message(String id,String role,String content){return new MessagePO(id,"s","t",role,content,"COMPLETED",null,"old",null,now);}
    CustomerServiceRunRequest submit(List<MessagePO> source){
        when(repository.listCompletedHistory(any(),any(),eq(12))).thenReturn(source);
        service.submit("t","u","s","customer-service-message/1","current input","request");
        var capture=org.mockito.ArgumentCaptor.forClass(CustomerServiceRunRequest.class);
        verify(ai).submitCustomerServiceMessage(eq("s"),capture.capture());return capture.getValue();
    }
    @Test void userHistoryUsesRegisteredContentDigestAndPreservesKnownAssistant()throws Exception {
        String content="known user question";
        String digest=HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(content.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        when(dependencies.dependencies(any(),eq("MESSAGE"),eq("U"),eq(digest))).thenReturn(List.of(a));
        when(dependencies.dependencies(any(),eq("MESSAGE"),eq("R"),eq("1"))).thenReturn(List.of(a));
        var request=submit(List.of(message("U","USER",content),message("R","ASSISTANT","known answer")));
        assertEquals(List.of(content,"known answer"),request.history().stream().map(CustomerServiceRunRequest.HistoryMessage::content).toList());
    }
    @Test void projectedHistoryRetainsNewestCompleteGroupWithinOriginalCharacterLimit() {
        when(dependencies.dependencies(any(),eq("MESSAGE"),eq("old"),eq("1"))).thenReturn(List.of(a));
        when(dependencies.dependencies(any(),eq("MESSAGE"),eq("new"),eq("1"))).thenReturn(List.of(b));
        var request=submit(List.of(message("old","ASSISTANT","A".repeat(7000)),message("new","ASSISTANT","B".repeat(7000))));
        assertEquals(1,request.history().size());assertEquals("B".repeat(7000),request.history().get(0).content());
        verify(packets).issueMessage(any(),any(),any(),any(),eq(List.of(b)));
    }
    @Test void operationsKeepsEightWholeRecentMessagesAndRejectsUnknownAndForeignHistory() {
        var scope=new com.aiep.aihub.api.memory.MemoryScopeDTO("t","u","operations","operations","CONVERSATION","s");
        when(dependencies.dependencies(eq(scope),eq("MESSAGE"),any(),eq("1"))).thenReturn(List.of(a));
        var messages=new ArrayList<MemoryHistoryProjection.Message>();
        for(int i=0;i<10;i++)messages.add(MemoryHistoryProjection.message(scope,"message-"+i,"assistant","body"+i));
        var projection=new MemoryHistoryProjection(dependencies);
        var selected=projection.selectBounded(scope,messages,8,12000);
        assertEquals(8,selected.size());assertEquals("message-2",selected.get(0).id());assertEquals("message-9",selected.get(7).id());
        assertTrue(projection.selectBounded(new com.aiep.aihub.api.memory.MemoryScopeDTO("t","other","operations","operations","CONVERSATION","s"),messages,8,12000).isEmpty());
    }
}
