package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.MemoryDeletionDispatcher;
import com.aiep.aihub.repository.memory.MemoryMapper;
import com.fasterxml.jackson.databind.JsonNode;
import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.sql.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import static org.junit.jupiter.api.Assertions.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;

/** 唯一Fake是complete-only模型；内部测试握手仅固定真实取消/流调度，不代替任何ACK或持久组件。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class PrivateMemoryInflightIntegrationTest {
    static final HttpClient HTTP=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    static String agentBase,secret;
    static Process startAgent(String suffix)throws Exception{
        var root=Path.of("../..").toAbsolutePath().normalize();
        return new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),"-m","tests.integration.context_control.private_memory_inflight_fixture")
            .directory(root.resolve("efficiency-platform-agent").toFile()).redirectErrorStream(true)
            .redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/D17INFLIGHT-agent-"+suffix+".log").toFile()).start();
    }
    static void ready(Process process)throws Exception{
        long deadline=System.nanoTime()+Duration.ofSeconds(30).toNanos();
        while(System.nanoTime()<deadline){
            assertTrue(process.isAlive(),"隔离Agent退出；只查看安全fixture日志");
            try{if(HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/health/live")).timeout(Duration.ofSeconds(1)).GET().build(),HttpResponse.BodyHandlers.discarding()).statusCode()==200)return;}catch(IOException unavailable){}
            Thread.sleep(50);
        }
        fail("隔离Agent启动超时");
    }
    static JsonNode agent(String path,boolean post)throws Exception{
        var builder=HttpRequest.newBuilder(URI.create(agentBase+path)).header("Authorization","Bearer "+secret).header("X-Tenant-ID","t1").timeout(Duration.ofSeconds(12));
        var result=HTTP.send(post?builder.POST(HttpRequest.BodyPublishers.noBody()).build():builder.GET().build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(200,result.statusCode(),"仅内部握手状态不符；不输出响应正文");return JSON.readTree(result.body());
    }
    static void stopAgent(Process process)throws Exception{
        if(!process.isAlive())return;
        agent("/__memory_it__/inflight/release-exit",true);agent("/__memory_it__/inflight/release-reader",true);
        agent("/__memory_it__/shutdown",true);
        assertTrue(process.waitFor(20,TimeUnit.SECONDS),"Agent应完成自有任务/PGschema清理后退出");
    }
    @Test void actualInflightOwnerMustExitBeforeCleanupAckAndOpenedReaderCannotReplayAfterForget()throws Exception{
        var ds=checkedLifecycleDataSource();seedLifecycle(ds);
        secret=required("MEMORY_IT_INTERNAL_SECRET");agentBase="http://127.0.0.1:"+required("MEMORY_IT_AGENT_PORT");
        PrivateMemoryLifecycleIntegrationTest.secret=secret;PrivateMemoryLifecycleIntegrationTest.agentBase=agentBase;
        Process process=startAgent("first");var executor=Executors.newFixedThreadPool(2);
        try{
            ready(process);
            var app=new SpringApplication(PrivateMemoryLifecycleIntegrationTest.ITConfiguration.class);
            app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false","aiep.memory.packet-enabled","true","aiep.memory.deletion-worker-enabled","true"));
            String execution;
            try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")){
                PrivateMemoryLifecycleIntegrationTest.javaBase="http://127.0.0.1:"+context.getWebServer().getPort();
                String token=TOKENS.get("t1:u1"),session=SESSIONS.get("t1:u1:operations:1");
                var saved=PrivateMemoryLifecycleIntegrationTest.postJava("/api/aihub/memories",token,command("operations",session,"response.language","zh-CN",0,"inflight-save"),200).path("data");
                String message=JSON.writeValueAsString(Map.of("message","d17-inflight-hold解释一种常见概念","clientRequestId","inflight-original"));
                var submitted=PrivateMemoryLifecycleIntegrationTest.postJava("/api/operations/conversations/"+session+"/messages",token,message,202).path("data");
                var entered=agent("/__memory_it__/inflight/wait/entered",false);
                execution=entered.path("execution_id").asText();String runtime=entered.path("runtime_id").asText();
                assertEquals(submitted.path("runId").asText(),execution);assertEquals(1,entered.path("direct_calls").asInt());
                int providerCalls=entered.path("provider_calls").asInt();long originalDeadline;
                try(var c=ds.getConnection();var q=c.prepareStatement("SELECT original_deadline FROM agent_memory_execution WHERE tenant_id='t1' AND execution_id=?")){q.setBytes(1,MemoryMapper.identity(execution));try(var rows=q.executeQuery()){assertTrue(rows.next());originalDeadline=rows.getLong(1);}}
                assertTrue(agent("/__memory_it__/inflight/seed-buffer",true).path("accepted").asBoolean());
                var stream=HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/v1/runs/"+runtime+"/events")).header("X-Tenant-ID","t1").header("Authorization","Bearer "+secret).GET().build(),HttpResponse.BodyHandlers.ofInputStream());
                assertEquals(200,stream.statusCode());
                try(var reader=new BufferedReader(new InputStreamReader(stream.body(),StandardCharsets.UTF_8))){
                    String line;boolean firstEvent=false;while((line=reader.readLine())!=null){if(line.isEmpty()){firstEvent=true;break;}assertFalse(line.contains("synthetic-inflight-private-marker"));}assertTrue(firstEvent);
                    assertTrue(agent("/__memory_it__/inflight/wait/reader_open",false).path("observed").asBoolean());
                    var forgotten=PrivateMemoryLifecycleIntegrationTest.postJava("/api/aihub/memory-deletions",token,JSON.writeValueAsString(Map.of("topAgent","operations","sessionId",session,"itemId",saved.path("id").asText(),"expectedRevision",saved.path("revision").asLong(),"idempotencyKey","inflight-forget")),200).path("data");
                    assertEquals("DELETE_PENDING",forgotten.path("status").asText());
                    var dispatch=executor.submit(()->context.getBean(MemoryDeletionDispatcher.class).dispatch());
                    assertTrue(agent("/__memory_it__/inflight/wait/cancel_seen",false).path("observed").asBoolean());
                    assertFalse(dispatch.isDone(),"worker不能在原Provider仍被退出gate阻塞时ACK");
                    try(var c=ds.getConnection();var q=c.prepareStatement("SELECT e.state,r.stop_confirmed,r.threads_receipt,r.scrub_receipt FROM agent_memory_execution e JOIN agent_memory_invalidation_receipt r ON r.tenant_id=e.tenant_id AND r.execution_id=e.execution_id WHERE e.tenant_id='t1' AND e.execution_id=?")){q.setBytes(1,MemoryMapper.identity(execution));try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals("REVOKED",rows.getString(1));assertFalse(rows.getBoolean(2));assertNull(rows.getString(3));assertNull(rows.getString(4));}}
                    var pending=PrivateMemoryLifecycleIntegrationTest.getJava("/api/aihub/memory-deletions/"+forgotten.path("jobId").asText()+"?topAgent=operations&sessionId="+session,token,200).path("data");assertEquals("DELETE_PENDING",pending.path("status").asText());
                    agent("/__memory_it__/inflight/release-exit",true);dispatch.get(30,TimeUnit.SECONDS);
                    assertTrue(agent("/__memory_it__/inflight/wait/exited",false).path("observed").asBoolean());
                    var done=PrivateMemoryLifecycleIntegrationTest.getJava("/api/aihub/memory-deletions/"+forgotten.path("jobId").asText()+"?topAgent=operations&sessionId="+session,token,200).path("data");assertEquals("DELETED",done.path("status").asText());assertEquals(6,done.path("completedTargets").asInt());
                    agent("/__memory_it__/inflight/release-reader",true);
                    String remaining=executor.submit(()->reader.lines().collect(java.util.stream.Collectors.joining("\n"))).get(10,TimeUnit.SECONDS);
                    assertFalse(remaining.contains("synthetic-inflight-private-marker"),"遗忘截止点之后已打开reader不能吐出旧缓冲正文");
                    var late=agent("/__memory_it__/inflight/late-publish",true);assertFalse(late.path("accepted").asBoolean());assertEquals(providerCalls,late.path("provider_calls").asInt());
                    agent("/__memory_it__/inflight/release-exit",true);context.getBean(MemoryDeletionDispatcher.class).dispatch();
                    var replay=PrivateMemoryLifecycleIntegrationTest.postJava("/api/operations/conversations/"+session+"/messages",token,message,202).path("data");assertEquals(execution,replay.path("runId").asText());
                    assertEquals(providerCalls,agent("/__memory_it__/inflight/late-publish",true).path("provider_calls").asInt());
                    MemoryForgetIntegrationTest.assertBody(ds,saved.path("id").asText(),saved.path("versionId").asText(),true);
                    try(var c=ds.getConnection();var q=c.prepareStatement("SELECT state,snapshot_ciphertext,snapshot_nonce,original_deadline FROM agent_memory_execution WHERE tenant_id='t1' AND execution_id=?")){q.setBytes(1,MemoryMapper.identity(execution));try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals("SCRUBBED",rows.getString(1));assertNull(rows.getBytes(2));assertNull(rows.getBytes(3));assertEquals(originalDeadline,rows.getLong(4));}}
                }
            }
            stopAgent(process);process=startAgent("restarted");ready(process);
            var afterRestart=agent("/__memory_it__/inflight/authority/"+execution,false);assertTrue(afterRestart.path("revoked").asBoolean());assertEquals(0,afterRestart.path("provider_calls").asInt());
            System.out.println("D17 inflight actualOwnerJoin=true preExitNoAck=true openedReaderNoLateBody=true providerCallsUnchanged=true restartedAuthorityRevoked=true");
        }finally{
            try{stopAgent(process);}finally{if(process.isAlive()){process.destroy();if(!process.waitFor(5,TimeUnit.SECONDS))process.destroyForcibly();}executor.shutdownNow();}
        }
    }
    static DataSource checkedLifecycleDataSource()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");assertTrue(url.startsWith("jdbc:mysql://"));
        var uri=URI.create(url.substring(5));assertNull(uri.getUserInfo());assertEquals("127.0.0.1",uri.getHost());
        String schema=uri.getPath().substring(1);assertTrue(schema.matches("aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        try(var connection=ds.getConnection()){
            assertEquals("MySQL",connection.getMetaData().getDatabaseProductName());
            try(var statement=connection.createStatement();var rows=statement.executeQuery("SELECT DATABASE()")){assertTrue(rows.next());assertEquals(schema,rows.getString(1));}
            var actual=new HashSet<String>();
            try(var statement=connection.createStatement();var rows=statement.executeQuery("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'ai\\_memory\\_%'")){while(rows.next())actual.add(rows.getString(1));}
            assertEquals(Set.of("ai_memory_session_binding","ai_memory_policy","ai_memory_policy_version","ai_memory_item","ai_memory_version","ai_memory_source","ai_memory_dependency","ai_memory_decision","ai_memory_suppression","ai_memory_outbox","ai_memory_deletion_job","ai_memory_tombstone","ai_memory_packet"),actual);
        }
        return ds;
    }
    static void seedLifecycle(DataSource ds)throws Exception {
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message","ai_operation_run","ai_operation_artifact"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");
            for(String table:List.of("ai_customer_service_message","ai_customer_service_run","ai_customer_service_run_step","ai_agent_definition","ai_agent_release"))sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql",table);
            String customerIncrement=Files.readString(Path.of("../sql/migration/V1.1.5__align_customer_service_runtime_columns.sql")).replaceAll("(?m)--[^\\r\\n]*","");
            for(String statement:customerIncrement.split(";"))if(!statement.isBlank())try(var s=c.createStatement()){s.execute(statement);}
            sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_session");sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql","id_hr_grant");
            for(String statement:Files.readString(Path.of("../sql/migration/V1.0.1__operation_assistant_artifact_versions.sql")).split(";"))
                if(!statement.isBlank())try(var s=c.createStatement()){s.execute(statement);}
            seed(c);
            try(var s=c.createStatement()) {
                s.execute("INSERT INTO ai_agent_definition(id,agent_key,name,agent_type,status,created_by,created_at,updated_by,updated_at) VALUES('b0900000-0000-0000-0000-000000000002','customer-service','synthetic','CUSTOMER_SERVICE','ACTIVE','test',UTC_TIMESTAMP(6),'test',UTC_TIMESTAMP(6))");
                s.execute("INSERT INTO ai_agent_release(id,agent_definition_id,agent_version_id,environment,release_status,released_by,released_at,created_at) VALUES('b0900000-0000-0000-0000-000000000001','b0900000-0000-0000-0000-000000000002','b0900000-0000-0000-0000-000000000003','dev','ACTIVE','test',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))");
            }
            for(String tenant:List.of("t1","t2")) for(String domain:List.of("operations","customer-service")) {
                String policy;
                try(var s=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id=? AND policy_id=? AND version_id=?")) {
                    s.setBytes(1,tenant.getBytes());s.setBytes(2,("policy-"+domain).getBytes());s.setBytes(3,"v1".getBytes());
                    try(var rows=s.executeQuery()){assertTrue(rows.next());policy=rows.getString(1);}
                }
                var published=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(policy);
                published.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"executionTimeoutSeconds",300,"sourceRetentionSeconds",1200,
                    "sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),
                    "executionGrants",List.of(Map.of("node_id",domain.equals("operations")?"intent":"customer-service:intent","execution_agent_id",domain,"purpose","intent"),Map.of("node_id",domain.equals("operations")?"direct":"customer-service:answer_general","execution_agent_id",domain,"purpose","assistant_response")))));
                try(var s=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES(?,?,?,?,?)")){
                    s.setBytes(1,tenant.getBytes());s.setBytes(2,("policy-"+domain).getBytes());s.setBytes(3,"memory/3".getBytes());s.setString(4,published.toString());s.setBytes(5,random(32));s.executeUpdate();}
                try(var s=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id=? WHERE tenant_id=? AND id=?")){
                    s.setBytes(1,"memory/3".getBytes());s.setBytes(2,tenant.getBytes());s.setBytes(3,("policy-"+domain).getBytes());s.executeUpdate();}
            }
        }
    }
}
