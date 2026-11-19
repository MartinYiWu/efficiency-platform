package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.*;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.sql.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
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
import static org.junit.jupiter.api.Assertions.*;

/** 正式MVC/Identity/Mapper→真实Agent/双库/原CSR栈；只有模型供应商为固定Fake。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshHttpIntegrationTest {
    static final ObjectMapper JSON=PrivateMemoryLifecycleIntegrationTest.JSON;
    static final HttpClient HTTP=PrivateMemoryLifecycleIntegrationTest.HTTP;
    @Configuration(proxyBeanMethods=false)
    @Import(MemoryContextResumeService.class)
    static class RefreshConfiguration extends PrivateMemoryLifecycleIntegrationTest.ITConfiguration {
        @Bean @Override SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception {
            var factory=super.sqlSessionFactory(ds);
            var resource=new ClassPathResource("mapper/memory/MemoryRefreshMapper.xml");
            try(var input=resource.getInputStream()) {
                new org.apache.ibatis.builder.xml.XMLMapperBuilder(input,factory.getConfiguration(),resource.getPath(),factory.getConfiguration().getSqlFragments()).parse();
            }
            return factory;
        }
        @Bean MemoryRefreshMapper refreshMapper(SqlSessionFactory factory){return new SqlSessionTemplate(factory).getMapper(MemoryRefreshMapper.class);}
    }

    @Test void customerInternalWaitRefreshesOriginalFrameAndPreservesIntentRevision()throws Exception {
        runRefreshScenario("answer_general");
    }

    static void runRefreshScenario(String waitNode)throws Exception {
        boolean intentWait=waitNode.equals("intent");
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        seedRefreshCase(ds);
        String secret=required("MEMORY_IT_INTERNAL_SECRET");String agentBase="http://127.0.0.1:"+Integer.parseInt(required("MEMORY_IT_AGENT_PORT"));
        PrivateMemoryLifecycleIntegrationTest.secret=secret;PrivateMemoryLifecycleIntegrationTest.agentBase=agentBase;
        var root=Path.of("../..").toAbsolutePath().normalize();
        var builder=new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),"-m","tests.integration.context_control.private_memory_refresh_fixture")
            .directory(root.resolve("efficiency-platform-agent").toFile()).redirectErrorStream(true)
            .redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/"+(intentWait?"D16RF07I":"D16RF07")+"-agent-http.log").toFile());
        builder.environment().put("MEMORY_IT_REFRESH_NODE",waitNode);
        var agent=builder.start();
        try {
            awaitAgent(agent,agentBase);
            var app=new SpringApplication(RefreshConfiguration.class);
            app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false","aiep.memory.packet-enabled","true","aiep.memory.refresh-enabled","true","aiep.memory.deletion-worker-enabled","false"));
            try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")) {
                String javaBase="http://127.0.0.1:"+context.getWebServer().getPort();PrivateMemoryLifecycleIntegrationTest.javaBase=javaBase;
                String credential=TOKENS.get("t1:u1"),session=SESSIONS.get("t1:u1:customer-service:1");
                PrivateMemoryLifecycleIntegrationTest.postJava("/api/aihub/memories",credential,command("customer-service",session,"response.language","zh-CN",0,"rf07-language"),200);
                var submitted=PrivateMemoryLifecycleIntegrationTest.postJava("/api/customer-service/conversations/"+session+"/messages",credential,
                    JSON.writeValueAsString(Map.of("contractVersion","customer-service-message/1","message","rf07 synthetic general advice","clientRequestId","rf07-csr")),200);
                String execution=submitted.path("data").path("runId").asText();assertFalse(execution.isBlank());
                var stream=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/customer-service/runs/"+execution+"/events"))
                    .header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(35)).GET().build(),HttpResponse.BodyHandlers.ofString());
                if(stream.statusCode()!=200||!stream.body().contains("event:run.completed"))printFailureProof(stream);
                assertEquals(200,stream.statusCode());assertTrue(stream.body().contains("event:message.delta"));assertTrue(stream.body().contains("event:run.completed"));
                assertFalse(stream.body().contains("context_refresh_required"));assertFalse(stream.body().contains("context_wait_ref"));
                var run=PrivateMemoryLifecycleIntegrationTest.getJava("/api/customer-service/runs/"+execution,credential,200).path("data");assertEquals("SUCCEEDED",run.path("status").asText());
                var packets=context.getBean(MemoryPacketMapper.class);var refresh=context.getBean(MemoryRefreshMapper.class);
                var original=packets.findPacket(MemoryMapper.identity("t1"),MemoryMapper.identity(execution));
                var anchor=refresh.findAnchor(MemoryMapper.identity("t1"),MemoryMapper.identity(execution));
                var current=refresh.findCurrent(MemoryMapper.identity("t1"),MemoryMapper.identity(execution));
                assertNotNull(original);assertNotNull(anchor);assertNotNull(current);assertEquals(1,original.packetRevision());
                assertTrue(original.originalDeadline()-original.issuedAt()>0&&original.originalDeadline()-original.issuedAt()<=60);
                assertEquals(3,anchor.policyTtlSeconds());assertEquals("ACKED",current.phase());assertEquals(2,current.targetRevision());assertEquals(1,current.refreshCount());
                assertTrue(current.issuedAt()>=original.expiresAt());assertTrue(current.expiresAt()-current.issuedAt()<=3);
                assertTrue(current.expiresAt()<=original.originalDeadline());assertTrue(current.expiresAt()<=anchor.sourceRetentionDeadline());
                String waitRef=new String(current.waitEventId(),java.nio.charset.StandardCharsets.UTF_8);assertFalse(stream.body().contains(waitRef));
                try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM ai_customer_service_run_step WHERE run_id=? AND (stage='context_refresh_required' OR internal_payload LIKE '%context_wait_ref%')")) {
                    q.setString(1,execution);try(var r=q.executeQuery()){assertTrue(r.next());assertEquals(0,r.getInt(1));}
                }
                var manifest=context.getBean(AiInvokeFacade.class).queryMemoryManifest("t1",execution);
                assertEquals(run.path("agentRunId").asText(),manifest.runtimeId());
                assertEquals(2,manifest.packetRevision());
                assertTrue(manifest.manifests().stream().anyMatch(item->item.nodeId().equals("customer-service:intent")&&item.packetRevision()==1));
                assertTrue(manifest.manifests().stream().anyMatch(item->item.nodeId().equals("customer-service:answer_general")&&item.packetRevision()==(intentWait?2:1)));
                assertFalse(context.getBean(MemoryPacketService.class).verifyManifest(context.getBean(MemoryPacketService.class).issuedScope("t1",execution),execution,manifest.runtimeId(),manifest).isEmpty());
                var proof=PrivateMemoryLifecycleIntegrationTest.proof();verifyProof(proof,execution,original.originalDeadline(),intentWait);
                int posts=proof.path("refresh_proof").path("internal_resume_posts").asInt();
                var replay=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/customer-service/runs/"+execution+"/events"))
                    .header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(5)).GET().build(),HttpResponse.BodyHandlers.ofString());
                assertEquals(200,replay.statusCode());assertFalse(replay.body().contains(waitRef));assertFalse(replay.body().contains("context_wait_ref"));
                assertEquals(posts,PrivateMemoryLifecycleIntegrationTest.proof().path("refresh_proof").path("internal_resume_posts").asInt());
                System.out.println((intentWait?"D16RF07I":"D16RF07")+" javaCSR=passed internalWaitHidden=true javaAcked=2 originalPacket=1 intentCalls=1 answerCalls=1 preparedManifests="+(intentWait?"1,2":"1,1")+" actualSentPacketRevisions="+(intentWait?"2,2":"1,2")+" terminalReplayNoResume=true paidCalls=0");
            }
        }finally {
            if(agent.isAlive())try {HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/__memory_it__/shutdown")).header("Authorization","Bearer "+secret).timeout(Duration.ofSeconds(2)).POST(HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());}catch(java.io.IOException unavailable){}
            if(!agent.waitFor(10,TimeUnit.SECONDS)){agent.destroy();if(!agent.waitFor(5,TimeUnit.SECONDS)){agent.destroyForcibly();assertTrue(agent.waitFor(5,TimeUnit.SECONDS));}}
        }
    }

    static void printFailureProof(HttpResponse<String> stream) {
        System.out.println("D16RF06I1 httpStatus="+stream.statusCode()+" completedEvent="+stream.body().contains("event:run.completed")+" failedEvent="+stream.body().contains("event:run.failed")+" accessRevoked="+stream.body().contains("MEMORY_ACCESS_REVOKED")+" bindingRequired="+stream.body().contains("MEMORY_RUN_BINDING_REQUIRED"));
        try {
            var proof=PrivateMemoryLifecycleIntegrationTest.proof();var refresh=proof.path("refresh_proof");
            int intents=0,answers=0;
            for(var request:proof.path("requests")) {
                if(request.path("node_id").asText().equals("customer-service:intent"))intents++;
                if(request.path("node_id").asText().equals("customer-service:answer_general"))answers++;
            }
            System.out.println("D16RF06I1 intentCalls="+intents+" answerCalls="+answers+" waitEvents="+refresh.path("wait_events").asInt()+" resumePosts="+refresh.path("internal_resume_posts").asInt()+" results="+refresh.path("results_count").asInt());
            for(var item:refresh.path("executions"))System.out.println("D16RF06I1 currentRevision="+item.path("packet_revision").asInt()+" refreshCount="+item.path("refresh_count").asInt());
            for(var operation:refresh.path("operations"))System.out.println("D16RF06I1 intentOperation="+operation.path("node_id").asText().equals("customer-service:intent")+" manifestRevision="+operation.path("packet_revision").asInt()+" sentRevision="+operation.path("actual_sent_packet_revision").asInt());
        }catch(Exception unavailable) {
            System.out.println("D16RF06I1 proofAvailable=false");
        }
    }

    static void verifyProof(JsonNode proof,String execution,long deadline,boolean intentWait) {
        int intents=0,answers=0;
        for(var request:proof.path("requests"))if(execution.equals(request.path("execution_id").asText())) {
            if(request.path("node_id").asText().equals("customer-service:intent"))intents++;
            if(request.path("node_id").asText().equals("customer-service:answer_general"))answers++;
        }
        assertEquals(1,intents);assertEquals(1,answers);
        var refresh=proof.path("refresh_proof");assertEquals(1,refresh.path("delayed_finalizes").asInt());assertEquals(1,refresh.path("wait_events").asInt());
        assertEquals(1,refresh.path("internal_wait_gets").asInt());assertEquals(1,refresh.path("internal_resume_posts").asInt());assertEquals(2,refresh.path("results_count").asInt());
        int executions=0;
        for(var item:refresh.path("executions"))if(execution.equals(item.path("execution_id").asText())) {
            executions++;assertEquals("ACTIVE",item.path("state").asText());assertEquals("ACTIVE",item.path("pg_state").asText());assertEquals(2,item.path("packet_revision").asInt());
            assertEquals(1,item.path("execution_revision").asInt());assertEquals(1,item.path("refresh_count").asInt());assertEquals(deadline,item.path("original_deadline").asLong());
            assertNotEquals(item.path("original_context_fingerprint").asText(),item.path("current_context_fingerprint").asText());assertEquals(item.path("current_context_fingerprint").asText(),item.path("pg_current_context_fingerprint").asText());
            assertTrue(item.path("current_context_fingerprint").asText().matches("[0-9a-f]{64}"));
        }
        assertEquals(1,executions);int operations=0;
        for(var operation:refresh.path("operations")) {
            operations++;assertEquals(1,operation.path("attempt").asInt());assertEquals("SUCCEEDED",operation.path("status").asText());
            assertTrue(Set.of("customer-service:intent","customer-service:answer_general").contains(operation.path("node_id").asText()));assertFalse(operation.path("operation_id").asText().isBlank());
            assertEquals(intentWait&&operation.path("node_id").asText().equals("customer-service:answer_general")?2:1,operation.path("packet_revision").asInt());
            assertEquals(!intentWait&&operation.path("node_id").asText().equals("customer-service:intent")?1:2,operation.path("actual_sent_packet_revision").asInt());
        }
        assertEquals(2,operations);assertEquals(1,refresh.path("refreshes").size());var receipt=refresh.path("refreshes").get(0);
        assertEquals("ACKED",receipt.path("phase").asText());assertEquals(1,receipt.path("old_packet_revision").asInt());assertEquals(2,receipt.path("target_packet_revision").asInt());assertEquals(1,receipt.path("refresh_count").asInt());assertTrue(receipt.path("body_encrypted").asBoolean());assertTrue(receipt.path("dispatch_allowed").asBoolean());
    }

    static void seedRefreshCase(DataSource ds)throws Exception {
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message","ai_operation_run","ai_operation_artifact"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            for(String table:List.of("ai_customer_service_conversation","ai_customer_service_message","ai_customer_service_run","ai_customer_service_run_step","ai_agent_definition","ai_agent_release"))sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql",table);
            for(String table:List.of("id_hr_session","id_hr_grant"))sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql",table);
            for(String statement:Files.readString(Path.of("../sql/migration/V1.1.5__align_customer_service_runtime_columns.sql")).replaceAll("(?m)--[^\\r\\n]*","").split(";"))if(!statement.isBlank())try(var q=c.createStatement()){q.execute(statement);}
            seed(c);
            try(var q=c.createStatement()) {
                q.execute("INSERT INTO ai_agent_definition(id,agent_key,name,agent_type,status,created_by,created_at,updated_by,updated_at) VALUES('b0900000-0000-0000-0000-000000000002','customer-service','synthetic','CUSTOMER_SERVICE','ACTIVE','test',UTC_TIMESTAMP(6),'test',UTC_TIMESTAMP(6))");
                q.execute("INSERT INTO ai_agent_release(id,agent_definition_id,agent_version_id,environment,release_status,released_by,released_at,created_at) VALUES('b0900000-0000-0000-0000-000000000001','b0900000-0000-0000-0000-000000000002','b0900000-0000-0000-0000-000000000003','dev','ACTIVE','test',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))");
            }
            String raw;try(var q=c.createStatement();var r=q.executeQuery("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id='policy-customer-service' AND version_id='v1'")){assertTrue(r.next());raw=r.getString(1);}
            var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
            policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",3,"executionTimeoutSeconds",60,"sourceRetentionSeconds",1200,"sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),"executionGrants",List.of(Map.of("node_id","customer-service:intent","execution_agent_id","customer-service","purpose","intent"),Map.of("node_id","customer-service:answer_general","execution_agent_id","customer-service","purpose","assistant_response")))));
            try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1','policy-customer-service','rf07/1',?,?)")){q.setString(1,policy.toString());q.setBytes(2,random(32));assertEquals(1,q.executeUpdate());}
            try(var q=c.createStatement()){assertEquals(1,q.executeUpdate("UPDATE ai_memory_policy SET current_version_id='rf07/1' WHERE tenant_id='t1' AND id='policy-customer-service'"));}
        }
    }
    static void awaitAgent(Process agent,String base)throws Exception {
        long until=System.nanoTime()+Duration.ofSeconds(30).toNanos();var probe=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build();
        while(System.nanoTime()<until) {
            assertTrue(agent.isAlive(),"RF07 Agent fixture退出，查看本机安全日志");
            try {if(probe.send(HttpRequest.newBuilder(URI.create(base+"/health/live")).timeout(Duration.ofSeconds(1)).GET().build(),HttpResponse.BodyHandlers.discarding()).statusCode()==200)return;}catch(java.io.IOException unavailable){}
            Thread.sleep(100);
        }
        fail("RF07 Agent fixture启动超时");
    }
}
