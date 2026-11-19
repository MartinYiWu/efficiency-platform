package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.MemoryPacketService;
import com.aiep.aihub.repository.memory.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Files;
import java.sql.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static com.aiep.aihub.memory.MemoryRefreshHttpIntegrationTest.JSON;
import static com.aiep.aihub.memory.MemoryRefreshHttpIntegrationTest.HTTP;
import static org.junit.jupiter.api.Assertions.*;

/** 正式OPS事件触发CPU Graph恢复；真实checkpoint/双库/内部HTTP，模型固定Fake。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshOperationHttpIntegrationTest {
    @Test void operationCpuWaitResumesOriginalGraphAndDispatchesDirectOnlyOnce()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        MemoryRefreshHttpIntegrationTest.seedRefreshCase(ds);
        try(var c=ds.getConnection()) {
            for(String statement:Files.readString(Path.of("../sql/migration/V1.0.1__operation_assistant_artifact_versions.sql")).split(";"))
                if(!statement.isBlank())try(var q=c.createStatement()){q.execute(statement);}
        }
        publishOperationPolicy(ds);
        String secret=required("MEMORY_IT_INTERNAL_SECRET"),agentBase="http://127.0.0.1:"+Integer.parseInt(required("MEMORY_IT_AGENT_PORT"));
        PrivateMemoryLifecycleIntegrationTest.secret=secret;PrivateMemoryLifecycleIntegrationTest.agentBase=agentBase;
        var root=Path.of("../..").toAbsolutePath().normalize();
        var builder=new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),"-m","tests.integration.context_control.private_memory_refresh_fixture")
            .directory(root.resolve("efficiency-platform-agent").toFile()).redirectErrorStream(true)
            .redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/D16RF07O-agent-http.log").toFile());
        builder.environment().put("MEMORY_IT_REFRESH_DOMAIN","operations");
        var agent=builder.start();
        try {
            MemoryRefreshHttpIntegrationTest.awaitAgent(agent,agentBase);
            var app=new SpringApplication(MemoryRefreshHttpIntegrationTest.RefreshConfiguration.class);
            app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false","aiep.memory.packet-enabled","true","aiep.memory.refresh-enabled","true","aiep.memory.deletion-worker-enabled","false"));
            try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")) {
                String javaBase="http://127.0.0.1:"+context.getWebServer().getPort();PrivateMemoryLifecycleIntegrationTest.javaBase=javaBase;
                String credential=TOKENS.get("t1:u1"),session=SESSIONS.get("t1:u1:operations:1");
                PrivateMemoryLifecycleIntegrationTest.postJava("/api/aihub/memories",credential,command("operations",session,"response.language","zh-CN",0,"rf07-ops-language"),200);
                var submitted=PrivateMemoryLifecycleIntegrationTest.postJava("/api/operations/conversations/"+session+"/messages",credential,
                    JSON.writeValueAsString(Map.of("message","rf07 synthetic operation advice","clientRequestId","rf07-ops")),202);
                String execution=submitted.path("data").path("runId").asText();assertFalse(execution.isBlank());
                var stream=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/operations/runs/"+execution+"/events"))
                    .header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(35)).GET().build(),HttpResponse.BodyHandlers.ofString());
                assertEquals(200,stream.statusCode());assertTrue(stream.body().contains("event:assistant_delta"));assertTrue(stream.body().contains("event:stream_done"));
                assertFalse(stream.body().contains("context_refresh_required"));assertFalse(stream.body().contains("wait_event_id"));
                var run=PrivateMemoryLifecycleIntegrationTest.getJava("/api/operations/runs/"+execution,credential,200).path("data");assertEquals("succeeded",run.path("status").asText());
                var packets=context.getBean(MemoryPacketMapper.class);var refresh=context.getBean(MemoryRefreshMapper.class);
                var original=packets.findPacket(b("t1"),b(execution));var anchor=refresh.findAnchor(b("t1"),b(execution));var current=refresh.findCurrent(b("t1"),b(execution));
                assertNotNull(original);assertNotNull(anchor);assertNotNull(current);assertEquals(1,original.packetRevision());assertEquals(1,original.executionRevision());
                assertEquals(3,anchor.policyTtlSeconds());assertTrue(original.originalDeadline()>original.issuedAt()&&original.originalDeadline()-original.issuedAt()<=60);
                assertEquals(original.originalDeadline(),anchor.originalDeadline());assertEquals("ACKED",current.phase());assertEquals(2,current.targetRevision());assertEquals(1,current.refreshCount());
                assertTrue(current.issuedAt()>=original.expiresAt());assertTrue(current.expiresAt()-current.issuedAt()<=3);assertTrue(current.expiresAt()<=anchor.originalDeadline());assertTrue(current.expiresAt()<=anchor.sourceRetentionDeadline());
                String waitRef=new String(current.waitEventId(),StandardCharsets.UTF_8);assertFalse(stream.body().contains(waitRef));assertFalse(stream.body().contains(new String(anchor.originalSessionRef(),StandardCharsets.UTF_8)));
                var identity=context.getBean(com.aiep.identity.api.IdentityFacade.class);assertEquals(identity.authenticate(credential).orElseThrow().sessionRef(),new String(anchor.originalSessionRef(),StandardCharsets.UTF_8));
                var manifest=context.getBean(AiInvokeFacade.class).queryMemoryManifest("t1",execution);
                assertEquals(run.path("agentRunId").asText(),manifest.runtimeId());assertEquals(2,manifest.packetRevision());assertEquals(2,manifest.manifests().size());
                assertTrue(manifest.manifests().stream().anyMatch(item->item.nodeId().equals("intent")&&item.packetRevision()==1));
                assertTrue(manifest.manifests().stream().anyMatch(item->item.nodeId().equals("direct")&&item.packetRevision()==2));
                assertFalse(context.getBean(MemoryPacketService.class).verifyManifest(context.getBean(MemoryPacketService.class).issuedScope("t1",execution),execution,manifest.runtimeId(),manifest).isEmpty());
                var proof=PrivateMemoryLifecycleIntegrationTest.proof();verifyOperationProof(proof,execution,manifest.runtimeId(),original.originalDeadline());
                int posts=proof.path("refresh_proof").path("internal_resume_posts").asInt();
                var replay=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/operations/runs/"+execution+"/events?afterSequence="+run.path("lastEventSequence").asLong()))
                    .header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(5)).GET().build(),HttpResponse.BodyHandlers.ofString());
                assertEquals(200,replay.statusCode());assertFalse(replay.body().contains(waitRef));assertFalse(replay.body().contains("context_refresh_required"));
                assertEquals(posts,PrivateMemoryLifecycleIntegrationTest.proof().path("refresh_proof").path("internal_resume_posts").asInt());
                System.out.println("D16RF07O javaOPS=passed graphCpuWait=BEFORE_PREPARE checkpoint=officialOwned resumeStart=DONE javaAcked=2 originalPacket=1 intentCalls=1 directCalls=1 manifestRevisions=1,2 actualSentPacketRevisions=1,2 publicWaitHidden=true terminalReplayNoResume=true paidCalls=0");
            }
        }finally {
            if(agent.isAlive())try {HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/__memory_it__/shutdown")).header("Authorization","Bearer "+secret).timeout(Duration.ofSeconds(2)).POST(HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());}catch(java.io.IOException unavailable){}
            if(!agent.waitFor(10,TimeUnit.SECONDS)){agent.destroy();if(!agent.waitFor(5,TimeUnit.SECONDS)){agent.destroyForcibly();assertTrue(agent.waitFor(5,TimeUnit.SECONDS));}}
        }
    }

    static void verifyOperationProof(JsonNode proof,String execution,String runtime,long deadline) {
        int intents=0,directs=0;
        for(var request:proof.path("requests"))if(execution.equals(request.path("execution_id").asText())) {
            if(request.path("node_id").asText().equals("intent"))intents++;
            if(request.path("node_id").asText().equals("direct"))directs++;
        }
        assertEquals(1,intents);assertEquals(1,directs);int completed=0;
        for(var run:proof.path("runs"))if(runtime.equals(run.path("id").asText())){completed++;assertEquals("succeeded",run.path("status").asText());assertTrue(run.path("encrypted").asBoolean());}
        assertEquals(1,completed);
        var refresh=proof.path("refresh_proof");assertEquals(1,refresh.path("delayed_finalizes").asInt());assertEquals(1,refresh.path("wait_events").asInt());
        assertEquals(1,refresh.path("internal_wait_gets").asInt());assertEquals(1,refresh.path("internal_resume_posts").asInt());assertEquals(2,refresh.path("results_count").asInt());
        assertEquals(1,refresh.path("executions").size());var owner=refresh.path("executions").get(0);
        assertEquals(execution,owner.path("execution_id").asText());assertEquals(runtime,owner.path("runtime_id").asText());
        assertEquals("ACTIVE",owner.path("state").asText());assertEquals("ACTIVE",owner.path("pg_state").asText());assertEquals(2,owner.path("packet_revision").asInt());
        assertEquals(1,owner.path("execution_revision").asInt());assertEquals(1,owner.path("refresh_count").asInt());assertEquals(deadline,owner.path("original_deadline").asLong());
        assertTrue(owner.path("current_context_fingerprint").asText().matches("[0-9a-f]{64}"));assertNotEquals(owner.path("original_context_fingerprint").asText(),owner.path("current_context_fingerprint").asText());assertEquals(owner.path("current_context_fingerprint").asText(),owner.path("pg_current_context_fingerprint").asText());
        assertEquals(2,refresh.path("operations").size());
        for(var operation:refresh.path("operations")) {
            assertTrue(Set.of("intent","direct").contains(operation.path("node_id").asText()));assertEquals("SUCCEEDED",operation.path("status").asText());assertEquals(1,operation.path("attempt").asInt());assertFalse(operation.path("operation_id").asText().isBlank());
            int revision=operation.path("node_id").asText().equals("intent")?1:2;assertEquals(revision,operation.path("packet_revision").asInt());assertEquals(revision,operation.path("actual_sent_packet_revision").asInt());
        }
        assertEquals(1,refresh.path("refreshes").size());var receipt=refresh.path("refreshes").get(0);
        assertEquals("ACKED",receipt.path("phase").asText());assertEquals(1,receipt.path("old_packet_revision").asInt());assertEquals(2,receipt.path("target_packet_revision").asInt());assertEquals(1,receipt.path("refresh_count").asInt());assertTrue(receipt.path("body_encrypted").asBoolean());assertTrue(receipt.path("dispatch_allowed").asBoolean());
        assertEquals(1,refresh.path("graph_waits").size());var graphWait=refresh.path("graph_waits").get(0);
        assertEquals("GRAPH",graphWait.path("checkpoint_mode").asText());assertEquals("BEFORE_PREPARE",graphWait.path("wait_phase").asText());assertEquals("DONE",graphWait.path("resume_start").asText());
        assertTrue(graphWait.path("checkpoint_id_present").asBoolean());assertTrue(graphWait.path("official_checkpoint_present").asBoolean());assertTrue(graphWait.path("owned_checkpoint_present").asBoolean());
    }

    static void publishOperationPolicy(DataSource ds)throws Exception {
        try(var c=ds.getConnection()) {
            String raw;try(var q=c.createStatement();var r=q.executeQuery("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id='policy-operations' AND version_id='v1'")){assertTrue(r.next());raw=r.getString(1);}
            var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
            policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",3,"executionTimeoutSeconds",60,"sourceRetentionSeconds",1200,"sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),"executionGrants",List.of(Map.of("node_id","intent","execution_agent_id","operations","purpose","intent"),Map.of("node_id","direct","execution_agent_id","operations","purpose","assistant_response")))));
            try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1','policy-operations','rf07-ops/1',?,?)")){q.setString(1,policy.toString());q.setBytes(2,random(32));assertEquals(1,q.executeUpdate());}
            try(var q=c.createStatement()){assertEquals(1,q.executeUpdate("UPDATE ai_memory_policy SET current_version_id='rf07-ops/1' WHERE tenant_id='t1' AND id='policy-operations'"));}
        }
    }
    static byte[] b(String value){return MemoryMapper.identity(value);}
}
