package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.web.memory.MemoryProposalController;
import com.aiep.aihub.web.memory.MemorySharingController;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.net.URI;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static com.aiep.aihub.memory.PrivateMemoryLifecycleIntegrationTest.postJava;
import static com.aiep.aihub.memory.PrivateMemoryLifecycleIntegrationTest.getJava;
import static org.junit.jupiter.api.Assertions.*;

/** 一条真实MVC/Identity/MySQL纵切；仅未调用的Agent边界拒绝替身，不启动模型或Agent进程。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryProposalSharingHttpIntegrationTest {
    static final AtomicInteger AGENT_CALLS=new AtomicInteger();

    @Configuration(proxyBeanMethods=false)
    @Import({MemorySummarySourceService.class,MemoryProposalService.class,MemoryConflictService.class,
        MemoryProposalController.class,MemoryScopeMembershipService.class,MemorySharingService.class,
        MemoryAgentGrantService.class,MemorySharingController.class})
    static class BusinessConfiguration extends MemoryRefreshHttpIntegrationTest.RefreshConfiguration {
        @Bean @Override AiInvokeFacade ai(){
            return (AiInvokeFacade)java.lang.reflect.Proxy.newProxyInstance(AiInvokeFacade.class.getClassLoader(),new Class<?>[]{AiInvokeFacade.class},(proxy,method,args)->{
                if(method.getDeclaringClass()==Object.class){
                    if(method.getName().equals("toString"))return "UnusedAgentBoundary";
                    if(method.getName().equals("hashCode"))return System.identityHashCode(proxy);
                    return proxy==args[0];
                }
                AGENT_CALLS.incrementAndGet();throw new AssertionError("CPU business flow called Agent");
            });
        }
        @Bean @Override SqlSessionFactory sqlSessionFactory(DataSource dataSource)throws Exception{
            var factory=super.sqlSessionFactory(dataSource);
            for(String name:List.of("MemorySummaryMapper","MemoryProposalMapper","MemorySharingMapper")){
                var resource=new ClassPathResource("mapper/memory/"+name+".xml");
                try(var input=resource.getInputStream()){
                    new org.apache.ibatis.builder.xml.XMLMapperBuilder(input,factory.getConfiguration(),resource.getPath(),factory.getConfiguration().getSqlFragments()).parse();
                }
            }
            return factory;
        }
        @Bean MemorySummaryMapper summaryMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemorySummaryMapper.class);}
        @Bean MemoryProposalMapper proposalMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryProposalMapper.class);}
        @Bean MemorySharingMapper sharingMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemorySharingMapper.class);}
    }

    @Test void pendingProposalConfirmsAfterOriginalExpiryAndExplicitGrantWithdrawsWithoutAgent()throws Exception{
        String jdbc=required("MEMORY_IT_MYSQL_JDBC_URL");var address=URI.create(jdbc.substring(5));
        assertEquals("127.0.0.1",address.getHost());assertTrue(address.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var dataSource=new DriverManagerDataSource(jdbc,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        AGENT_CALLS.set(0);MemoryRefreshHttpIntegrationTest.seedRefreshCase(dataSource);publishBusinessPolicy(dataSource);
        var app=new SpringApplication(BusinessConfiguration.class);
        var properties=new HashMap<String,Object>(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/",
            "server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false",
            "aiep.memory.packet-enabled","true","aiep.memory.refresh-enabled","true","aiep.memory.summary-persistence-enabled","true",
            "aiep.memory.proposals-enabled","true"));
        properties.put("aiep.memory.sharing-enabled","true");properties.put("aiep.memory.deletion-worker-enabled","false");app.setDefaultProperties(properties);
        try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")){
            PrivateMemoryLifecycleIntegrationTest.javaBase="http://127.0.0.1:"+context.getWebServer().getPort();
            String credential=TOKENS.get("t1:u1"),otherCredential=TOKENS.get("t1:u2"),session=SESSIONS.get("t1:u1:operations:1");
            var scope=new MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",session);
            var actor=context.getBean(IdentityFacade.class).authenticate(credential).orElseThrow();
            var dependencies=context.getBean(MemoryDependencyService.class);var packets=context.getBean(MemoryPacketMapper.class);
            MemorySummaryHttpIntegrationTest.seedGroup(dataSource,scope,packets,dependencies,List.of(),"请用中文回答。","好的。");
            var messages=messageGroup(dataSource,session);
            var current=dependencies.dependencies(scope,"MESSAGE",messages.getFirst(),hash("请用中文回答。"));
            assertFalse(current.isEmpty());
            String execution="cpu-proposal-execution",task="cpu-proposal-task";long deadline=Instant.now().getEpochSecond()+4;
            context.getBean(MemoryPacketService.class).issue(actor,scope,task,execution,JSON.valueToTree(Map.of("message","请用中文回答。")),deadline,current);
            var pending=postJava("/api/aihub/memories/proposals",credential,JSON.writeValueAsString(Map.of(
                "topAgent","operations","sessionId",session,"executionId",execution,"sourceMessageIds",messages,
                "candidates",List.of(Map.of("kind","PREFERENCE","fieldKey","response.language","value","zh-CN")),"idempotencyKey","proposal-user-explicit")),200).at("/data/proposals/0");
            assertEquals("PENDING",pending.path("status").asText());assertEquals("NOT_REQUESTED",pending.path("indexStatus").asText());
            String proposalId=pending.path("id").asText();assertFalse(proposalId.isBlank());
            getJava("/api/aihub/memories/proposals/"+proposalId+"?topAgent=operations&sessionId="+session,otherCredential,403);
            postJava("/api/aihub/memories/proposals/"+proposalId+"/decisions",credential,decision(session,pending.path("revision").asLong()+1,pending.path("expectedItemRevision").asLong(),"stale-proposal"),409);
            // 次日语义边界用原run真实过期模拟；来源/候选仍在各自合法保留期限，不延长原授权。
            long wait=Math.max(0,(deadline+1)*1000-System.currentTimeMillis());if(wait>0)Thread.sleep(wait);
            var expired=packets.findPacket(MemoryMapper.identity("t1"),MemoryMapper.identity(execution));assertTrue(expired.originalDeadline()<Instant.now().getEpochSecond());
            var accepted=postJava("/api/aihub/memories/proposals/"+proposalId+"/decisions",credential,decision(session,pending.path("revision").asLong(),pending.path("expectedItemRevision").asLong(),"confirm-nextday"),200).path("data");
            assertEquals("ACCEPTED",accepted.path("status").asText());assertEquals("NOT_REQUESTED",accepted.path("indexStatus").asText());assertFalse(accepted.path("versionId").asText().isBlank());
            var confirmed=getJava("/api/aihub/memories/"+accepted.path("itemId").asText()+"?topAgent=operations&sessionId="+session,credential,200).at("/data/preference");
            assertEquals(accepted.path("versionId").asText(),confirmed.path("versionId").asText());assertEquals("zh-CN",confirmed.path("value").asText());
            assertEquals(0,AGENT_CALLS.get());

            // 共享只用用户直接保存的独立偏好，不能把提炼确认的消息闭包洗成跨Agent权限。
            var original=postJava("/api/aihub/memories",credential,command("operations",session,"response.format","bullets",0,"direct-user-format"),200).path("data");
            var grant=postJava("/api/aihub/memory-sharing/agent-grants",credential,JSON.writeValueAsString(Map.of(
                "originAgent","operations","itemId",original.path("id").asText(),"versionId",original.path("versionId").asText(),"targetAgent","customer-service",
                "expectedItemRevision",original.path("revision").asLong(),"expiresAt",Instant.now().plusSeconds(300).toString(),"idempotencyKey","explicit-cross-agent")),200).path("data");
            assertEquals("ACTIVE",grant.path("status").asText());assertEquals("NOT_REQUESTED",grant.path("indexStatus").asText());
            var target=new MemoryScopeDTO("t1","u1","customer-service","customer-service","CONVERSATION",SESSIONS.get("t1:u1:customer-service:1"));
            var sharing=context.getBean(MemorySharingService.class);var selected=sharing.select(actor,target,Set.of("response.format"));
            assertEquals(1,selected.size());assertEquals("bullets",selected.getFirst().item().value());assertEquals("response.format",selected.getFirst().item().fieldKey());
            String oldProjection=selected.getFirst().item().itemId().replaceFirst("^share:","");
            var withdrawn=postJava("/api/aihub/memory-sharing/agent-grants/"+grant.path("id").asText()+"/withdrawals",credential,JSON.writeValueAsString(Map.of("expectedRevision",grant.path("revision").asLong(),"idempotencyKey","withdraw-cross-agent")),200).path("data");
            assertEquals("REVOKED",withdrawn.path("status").asText());assertTrue(sharing.select(actor,target,Set.of("response.format")).isEmpty());
            assertThrows(MemoryContracts.MemoryException.class,()->sharing.hydrate(actor,target,oldProjection));
            var retained=getJava("/api/aihub/memories/"+original.path("id").asText()+"?topAgent=operations&sessionId="+session,credential,200).at("/data/preference");
            assertEquals("bullets",retained.path("value").asText());assertEquals(original.path("versionId").asText(),retained.path("versionId").asText());
            assertEquals(0,AGENT_CALLS.get());
            System.out.println("D31BUSINESS proposal=PENDING->ACCEPTED originalRun=EXPIRED confirmation=CPU index=NOT_REQUESTED grant=ACTIVE->REVOKED target=filtered private=retained crossUser=403 staleRevision=409 agentCalls=0");
        }
    }

    static String decision(String session,long proposalRevision,long itemRevision,String request)throws Exception{
        return JSON.writeValueAsString(Map.of("topAgent","operations","sessionId",session,"expectedProposalRevision",proposalRevision,
            "expectedItemRevision",itemRevision,"action","CONFIRM","idempotencyKey",request));
    }
    static List<String> messageGroup(DataSource dataSource,String session)throws Exception{
        var result=new ArrayList<String>();try(var c=dataSource.getConnection();var q=c.prepareStatement("SELECT id FROM ai_operation_message WHERE tenant_id='t1' AND conversation_id=? ORDER BY created_at,id")){
            q.setString(1,session);try(var rows=q.executeQuery()){while(rows.next())result.add(rows.getString(1));}
        }assertEquals(2,result.size());return List.copyOf(result);
    }
    static void publishBusinessPolicy(DataSource dataSource)throws Exception{
        try(var c=dataSource.getConnection()){
            // 身份会话延长只用于模拟“执行已过期但用户仍在线”的CPU决策；不改变原run或来源截止。
            try(var q=c.createStatement()){q.executeUpdate("UPDATE id_hr_session SET expires_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 2 DAY)");}
            for(String domain:List.of("operations","customer-service")){
                ObjectNode policy;try(var q=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id=? AND version_id='v1'")){
                    q.setBytes(1,MemoryMapper.identity("policy-"+domain));try(var row=q.executeQuery()){assertTrue(row.next());policy=(ObjectNode)JSON.readTree(row.getString(1));}
                }
                policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"executionTimeoutSeconds",60,"sourceRetentionSeconds",1200,
                    "sourceTypes",List.of("CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION","MESSAGE","MEMORY_SHARE_GRANT"),
                    "executionGrants",List.of(Map.of("node_id",domain.equals("operations")?"direct":"customer-service:answer_general","execution_agent_id",domain,"purpose","assistant_response")),
                    "summary",Map.of("enabled",true,"mode","SUMMARY","purposes",List.of("SUMMARY"),"retentionSeconds",900,"maxPaidOperations",0))));
                policy.set("proposals",JSON.valueToTree(Map.of("enabled",true,"sourceTypes",List.of("MESSAGE","CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION"),"retentionSeconds",900)));
                policy.set("sharing",JSON.valueToTree(Map.of("enabled",true,"fields",List.of("response.language","response.detail_level","response.format"))));
                try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1',?,'business-cpu/1',?,?)")){
                    q.setBytes(1,MemoryMapper.identity("policy-"+domain));q.setString(2,policy.toString());q.setBytes(3,random(32));assertEquals(1,q.executeUpdate());
                }
                try(var q=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id='business-cpu/1' WHERE tenant_id='t1' AND id=?")){q.setBytes(1,MemoryMapper.identity("policy-"+domain));assertEquals(1,q.executeUpdate());}
            }
        }
    }
}
