package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.platformai.api.dto.*;
import com.fasterxml.jackson.databind.JsonNode;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.sql.*;
import java.time.*;
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
import static com.aiep.aihub.memory.MemoryRefreshHttpIntegrationTest.JSON;
import static com.aiep.aihub.memory.MemoryRefreshHttpIntegrationTest.HTTP;
import static org.junit.jupiter.api.Assertions.*;

/** 原OPS运行触发PaidHttp(MockTransport)派生，JavaCAS/finish后后续正常packet选择摘要。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemorySummaryHttpIntegrationTest {
    @Configuration(proxyBeanMethods=false)
    @Import({MemorySummarySourceService.class,MemorySummaryService.class})
    static class SummaryConfiguration extends MemoryRefreshHttpIntegrationTest.RefreshConfiguration {
        @Bean @Override com.aiep.platformai.api.AiInvokeFacade ai() {
            var delegate=super.ai();
            return (com.aiep.platformai.api.AiInvokeFacade)java.lang.reflect.Proxy.newProxyInstance(
                com.aiep.platformai.api.AiInvokeFacade.class.getClassLoader(),new Class<?>[]{com.aiep.platformai.api.AiInvokeFacade.class},(proxy,method,args)->{
                    boolean derive=method.getName().equals("deriveMemory");if(derive)System.out.println("M2_DERIVE_TRANSPORT entered=true");
                    try{return method.invoke(delegate,args);}catch(java.lang.reflect.InvocationTargetException wrapped){
                        var cause=wrapped.getCause();if(derive&&cause instanceof com.aiep.platformai.api.AiInvocationException failure)System.out.println("M2_DERIVE_TRANSPORT status="+failure.status()+" code="+failure.code());throw cause;
                    }
                });
        }
        @Bean MemoryDerivePlanService derivePlans(MemorySummarySourceService sources,MemorySummaryService summaries,
                com.aiep.platformai.api.AiInvokeFacade ai,com.aiep.aihub.repository.operation.OperationRunMapper operations,
                @org.springframework.beans.factory.annotation.Value("${aiep.memory.derive-enabled:false}") boolean enabled) {
            return new MemoryDerivePlanService(enabled,sources,summaries,ai,operations) {
                @Override public MemorySummaryContracts.SummarySegment generateAndCommit(IdentityFacade.Subject actor,MemoryScopeDTO scope,
                        String executionId,String planId,List<String> messages,MemoryDeriveRequest request) {
                    try{return super.generateAndCommit(actor,scope,executionId,planId,messages,request);}
                    catch(MemoryContracts.MemoryException failure){System.out.println("M2_DERIVE_REJECT layer=java code="+failure.code());throw failure;}
                    catch(com.aiep.platformai.api.AiInvocationException failure){System.out.println("M2_DERIVE_REJECT layer=transport status="+failure.status()+" code="+failure.code());throw failure;}
                }
            };
        }
        @Bean @Override SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception {
            var factory=super.sqlSessionFactory(ds);var resource=new ClassPathResource("mapper/memory/MemorySummaryMapper.xml");
            try(var in=resource.getInputStream()){new org.apache.ibatis.builder.xml.XMLMapperBuilder(in,factory.getConfiguration(),resource.getPath(),factory.getConfiguration().getSqlFragments()).parse();}
            return factory;
        }
        @Bean MemorySummaryMapper summaryMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemorySummaryMapper.class);}
    }
    @Test void originalControlDerivesOnceCommitsAndLaterNormalPacketAdoptsSummary()throws Exception {
        var originalTimezone=TimeZone.getDefault();
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            assertEquals(ZoneOffset.UTC,ZoneId.systemDefault().getRules().getOffset(Instant.now()));
            runOriginalControlScenario();
        }finally {TimeZone.setDefault(originalTimezone);}
    }
    private void runOriginalControlScenario()throws Exception {
        var uri=URI.create(required("MEMORY_IT_MYSQL_JDBC_URL").substring(5));assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        MemoryRefreshHttpIntegrationTest.seedRefreshCase(ds);
        try(var c=ds.getConnection()) {
            for(String stmt:Files.readString(Path.of("../sql/migration/V1.0.1__operation_assistant_artifact_versions.sql")).split(";"))if(!stmt.isBlank())try(var q=c.createStatement()){q.execute(stmt);}
            String raw;try(var q=c.createStatement();var r=q.executeQuery("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id='policy-operations' AND version_id='v1'")){assertTrue(r.next());raw=r.getString(1);}
            var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
            policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"executionTimeoutSeconds",120,"sourceRetentionSeconds",1200,
                "sourceTypes",List.of("CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION","MESSAGE","SUMMARY"),
                "executionGrants",List.of(Map.of("node_id","intent","execution_agent_id","operations","purpose","intent"),Map.of("node_id","direct","execution_agent_id","operations","purpose","assistant_response")),
                "summary",Map.of("enabled",true,"purposes",List.of("SUMMARY"),"retentionSeconds",900,"maxPaidOperations",1))));
            try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1','policy-operations','m2auto/2',?,?)")){q.setString(1,policy.toString());q.setBytes(2,random(32));assertEquals(1,q.executeUpdate());}
            try(var q=c.createStatement()){assertEquals(1,q.executeUpdate("UPDATE ai_memory_policy SET current_version_id='m2auto/2' WHERE tenant_id='t1' AND id='policy-operations'"));}
        }
        String secret=required("MEMORY_IT_INTERNAL_SECRET"),agentBase="http://127.0.0.1:"+required("MEMORY_IT_AGENT_PORT");
        PrivateMemoryLifecycleIntegrationTest.secret=secret;PrivateMemoryLifecycleIntegrationTest.agentBase=agentBase;
        var root=Path.of("../..").toAbsolutePath().normalize();var agent=new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),"-m","tests.integration.context_control.private_memory_summary_fixture")
            .directory(root.resolve("efficiency-platform-agent").toFile()).redirectErrorStream(true).redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/M2AUTO-agent-http.log").toFile()).start();
        try {
            MemoryRefreshHttpIntegrationTest.awaitAgent(agent,agentBase);
            var app=new SpringApplication(SummaryConfiguration.class);
            app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false",
                "aiep.memory.packet-enabled","true","aiep.memory.refresh-enabled","true","aiep.memory.summary-persistence-enabled","true","aiep.memory.derive-enabled","true"));
            try(var ctx=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")) {
                String javaBase="http://127.0.0.1:"+ctx.getWebServer().getPort();PrivateMemoryLifecycleIntegrationTest.javaBase=javaBase;
                String token=TOKENS.get("t1:u1"),session=SESSIONS.get("t1:u1:operations:1");
                var scope=new MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",session);
                var actor=ctx.getBean(IdentityFacade.class).authenticate(token).orElseThrow();
                var pref=ctx.getBean(MemoryPreferenceService.class).save(actor,new MemoryContracts.PreferenceCommand(scope,"response.language","zh-CN",0,"m2-auto-pref",null));
                var deps=ctx.getBean(MemoryDependencyService.class);var packets=ctx.getBean(MemoryPacketMapper.class);
                var prefDeps=deps.dependencies(scope,"MEMORY_VERSION",pref.id(),pref.versionId());
                // 一组原已完成普通长叙述，真实消息/source/decision，不伪造模型确认或原control。
                seedGroup(ds,scope,packets,deps,prefDeps,"Original notes. ".repeat(28),"Earlier advice. ".repeat(28));
                String first=submit(token,session,"M2 first advice"+" Context detail.".repeat(100),"m2-auto-first");var firstSse=events(javaBase,token,first);
                assertTrue(firstSse.contains("event:stream_done"));assertFalse(firstSse.contains("memory_derive_required"));assertFalse(firstSse.contains("baseline_ref"));
                assertEquals("succeeded",PrivateMemoryLifecycleIntegrationTest.getJava("/api/operations/runs/"+first,token,200).at("/data/status").asText());
                var proof=PrivateMemoryLifecycleIntegrationTest.proof().path("refresh_proof");
                var diagnostic=JSON.createObjectNode();for(String key:List.of("derive_events","derive_gets","derive_posts","finish_committed","finish_rejected","mock_provider_posts","ledger_calls","attempts","run_checks","budget_checks","baseline_checks"))diagnostic.set(key,proof.path(key));
                var direct=diagnostic.putArray("direct_measurements");for(var item:proof.path("summary_adoptions")){var measured=direct.addObject();for(String key:List.of("measurement","input_cap","prediction_basis","predicted_generation_tokens"))measured.set(key,item.path(key));}
                var initialPacket=packets.findPacket(MemoryMapper.identity("t1"),MemoryMapper.identity(first));var references=JSON.readTree(initialPacket.referencesJson());
                diagnostic.put("summary_refs_available",references.has("summary_context_refs"));diagnostic.put("derive_plan_available",references.has("derive_plan_id"));diagnostic.set("max_paid_operations",JSON.readTree(initialPacket.policyJson()).path("max_paid_operations"));
                var plans=diagnostic.putArray("java_plans");try(var c=ds.getConnection();var q=c.prepareStatement("SELECT state,transport_fingerprint IS NOT NULL,encrypted_payload IS NOT NULL FROM ai_memory_summary_plan WHERE tenant_id='t1' AND execution_id=?")){q.setBytes(1,MemoryMapper.identity(first));try(var r=q.executeQuery()){while(r.next()){var plan=plans.addObject();plan.put("state",r.getString(1));plan.put("transport_bound",r.getBoolean(2));plan.put("payload_encrypted",r.getBoolean(3));}}}
                try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_summary_source WHERE tenant_id='t1'")){try(var r=q.executeQuery()){assertTrue(r.next());diagnostic.put("java_source_count",r.getLong(1));}}
                System.out.println("M2AUTO_DIAGNOSTIC "+diagnostic);
                var summaries=ctx.getBean(MemorySummaryService.class);assertEquals(1,summaries.listCommitted(actor,scope).size());
                var committed=summaries.exportCommitted(actor,scope).getFirst();assertEquals("UNVERIFIED",summaries.listCommitted(actor,scope).getFirst().freeTextQuality());
                try(var c=ds.getConnection();var q=c.prepareStatement("SELECT state,transport_fingerprint,encrypted_payload FROM ai_memory_summary_plan WHERE tenant_id='t1' AND execution_id=?")){q.setBytes(1,MemoryMapper.identity(first));try(var r=q.executeQuery()){assertTrue(r.next());assertEquals("COMMITTED",r.getString(1));assertTrue(r.getString(2).matches("[0-9a-f]{64}"));assertNotNull(r.getBytes(3));}}
                assertEquals(1,proof.path("derive_events").asInt());assertEquals(1,proof.path("derive_posts").asInt());assertEquals(1,proof.path("finish_committed").asInt());assertEquals(0,proof.path("finish_rejected").asInt());
                assertEquals(1,proof.path("mock_provider_posts").asInt());assertEquals(1,proof.path("ledger_calls").asInt());assertEquals(1,proof.path("attempts").asInt());
                assertEquals("SUCCEEDED",proof.path("derive_operations").get(0).path("state").asText());assertTrue(proof.path("derive_operations").get(0).path("result_encrypted").asBoolean());
                var derive=proof.path("derive_manifests").get(0);assertEquals("derive-prompt/2",derive.path("prompt_version").asText());assertEquals("derive-schema/2",derive.path("output_schema_version").asText());assertTrue(derive.path("aliases_present").asBoolean());
                // 保最近原文合同不变：旧覆盖移出近期保护后才验证后续正常packet采用。
                for(int i=0;i<4;i++)seedGroup(ds,scope,packets,deps,prefDeps,"Recent note "+i,"Recent answer "+i);
                var historyRows=ctx.getBean(com.aiep.aihub.repository.operation.OperationMessageMapper.class).selectConversationMessages(session,"t1");
                var bounded=ctx.getBean(MemoryHistoryProjection.class).selectBounded(scope,historyRows.stream().map(item->MemoryHistoryProjection.message(scope,item.getId(),item.getRole(),item.getContent())).toList(),8,12000);
                var historySnapshot=bounded.stream().map(item->new MemoryHistoryMessage(item.id(),item.version(),item.role(),item.content(),deps.dependencies(scope,"MESSAGE",item.id(),item.version()))).toList();
                var completeHistory=MemorySummaryService.class.getDeclaredMethod("historyComplete",MemoryScopeDTO.class,List.class);completeHistory.setAccessible(true);
                var laterDiagnostic=JSON.createObjectNode();laterDiagnostic.put("history_count",bounded.size());laterDiagnostic.put("history_complete",(boolean)completeHistory.invoke(summaries,scope,historySnapshot));laterDiagnostic.put("covered_history_overlap",bounded.stream().filter(item->committed.coveredMessageIds().contains(item.id())).count());laterDiagnostic.put("committed_count",summaries.listCommitted(actor,scope).size());
                System.out.println("M2_LATER_HISTORY "+laterDiagnostic);
                assertTrue(laterDiagnostic.path("history_complete").asBoolean());assertEquals(0,laterDiagnostic.path("covered_history_overlap").asInt());
                String second=submit(token,session,"M2 later advice","m2-auto-later");var secondSse=events(javaBase,token,second);
                assertTrue(secondSse.contains("event:stream_done"));assertFalse(secondSse.contains("memory_derive_required"));
                var owner=packets.findPacket(MemoryMapper.identity("t1"),MemoryMapper.identity(second));
                var ownerDeps=JSON.readTree(owner.dependenciesJson());long summaryCount=0;for(var dependency:ownerDeps)if("SUMMARY".equals(dependency.path("source_type").asText()))summaryCount++;
                var laterRefs=JSON.readTree(owner.referencesJson());System.out.println("M2_LATER_PACKET "+JSON.writeValueAsString(Map.of("summary_source_count",summaryCount,"summary_refs_available",laterRefs.has("summary_context_refs"),"committed_count",summaries.listCommitted(actor,scope).size())));
                assertTrue(ownerDeps.toString().contains(committed.segment().segmentId()));
                var projection=JSON.readTree(owner.referencesJson()).path("summary_context_refs").asText();assertFalse(projection.contains("Advice"));
                var finalProof=PrivateMemoryLifecycleIntegrationTest.proof().path("refresh_proof");assertEquals(1,finalProof.path("mock_provider_posts").asInt());assertEquals(1,finalProof.path("derive_posts").asInt());
                for(var item:finalProof.path("summary_adoptions"))if(second.equals(item.path("execution_id").asText())){var later=JSON.createObjectNode();for(String key:List.of("status","aliases_present","before","after","measurement","input_cap","exclusion_reasons","selected_summary_tokens"))later.set(key,item.path(key));System.out.println("M2_LATER_ADOPTION "+later);}
                boolean adopted=false;for(var item:finalProof.path("summary_adoptions"))if(second.equals(item.path("execution_id").asText())){adopted=true;assertEquals("ADOPTED",item.path("status").asText());assertTrue(item.path("aliases_present").asBoolean());assertTrue(item.path("measurement").asLong()<=item.path("input_cap").asLong());assertEquals(item.path("measurement").asLong(),item.path("after").asLong());long summaryTokens=0;assertFalse(item.path("selected_summary_tokens").isEmpty());for(var size:item.path("selected_summary_tokens")){assertTrue(size.asLong()>0&&size.asLong()<=500);summaryTokens+=size.asLong();}assertTrue(summaryTokens<=1000);}
                assertTrue(adopted);
                System.out.println("M2AUTO javaAgent=passed originalControl=real paidHttp=MockTransport deriveCalls=1 attempts=1 cas=COMMITTED finish=COMMITTED laterNormalPacket=ADOPTED boundedContext=true summaryAliases=v2 recentProtection=retained realProviderCalls=0");
            }
        }finally {
            if(agent.isAlive())try {HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/__memory_it__/shutdown")).header("Authorization","Bearer "+secret).timeout(Duration.ofSeconds(2)).POST(HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());}catch(java.io.IOException unavailable){}
            if(!agent.waitFor(10,TimeUnit.SECONDS)){agent.destroy();if(!agent.waitFor(5,TimeUnit.SECONDS)){agent.destroyForcibly();agent.waitFor(5,TimeUnit.SECONDS);}}
        }
    }
    static String submit(String token,String session,String body,String request)throws Exception {
        return PrivateMemoryLifecycleIntegrationTest.postJava("/api/operations/conversations/"+session+"/messages",token,JSON.writeValueAsString(Map.of("message",body,"clientRequestId",request)),202).at("/data/runId").asText();
    }
    static String events(String base,String token,String run)throws Exception {
        var response=HTTP.send(HttpRequest.newBuilder(URI.create(base+"/api/operations/runs/"+run+"/events")).header("Authorization","Bearer "+token).timeout(Duration.ofSeconds(45)).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(200,response.statusCode());return response.body();
    }
    static void seedGroup(DataSource ds,MemoryScopeDTO scope,MemoryPacketMapper packets,MemoryDependencyService dependencies,List<MemoryContextPacket.Dependency> preference,String body,String answer)throws Exception {
        String run=UUID.randomUUID().toString(),user=UUID.randomUUID().toString(),assistant=UUID.randomUUID().toString();
        try(var c=ds.getConnection()) {
            LocalDateTime base;try(var q=c.prepareStatement("SELECT GREATEST(COALESCE(MAX(created_at),DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND)),DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND)) FROM ai_operation_message WHERE tenant_id='t1' AND conversation_id=?")){q.setString(1,scope.sessionId());try(var r=q.executeQuery()){assertTrue(r.next());base=r.getObject(1,LocalDateTime.class);}}
            var userAt=base.plusNanos(1000);var assistantAt=base.plusNanos(2000);
            try(var q=c.createStatement();var r=q.executeQuery("SELECT UTC_TIMESTAMP(6)")){assertTrue(r.next());assertFalse(assistantAt.isAfter(r.getObject(1,LocalDateTime.class)));}
            try(var q=c.prepareStatement("INSERT INTO ai_operation_run(id,conversation_id,tenant_id,user_message_id,agent_run_id,status,created_at,updated_at) VALUES(?,?,'t1',?,?,'succeeded',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))")){q.setString(1,run);q.setString(2,scope.sessionId());q.setString(3,user);q.setString(4,"synthetic-old-"+run);q.executeUpdate();}
            try(var q=c.prepareStatement("INSERT INTO ai_operation_message(id,conversation_id,tenant_id,role,content,run_id,created_at) VALUES(?,?,'t1','user',?,?,?),(?,?,'t1','assistant',?,?,?)")){q.setString(1,user);q.setString(2,scope.sessionId());q.setString(3,body);q.setString(4,run);q.setObject(5,userAt);q.setString(6,assistant);q.setString(7,scope.sessionId());q.setString(8,answer);q.setString(9,run);q.setObject(10,assistantAt);q.executeUpdate();}
        }
        String hash=hash(body),source=UUID.randomUUID().toString();packets.insertInputSource(MemoryMapper.identity("t1"),MemoryMapper.identity(source),MemoryMapper.identity(user),MemoryMapper.identity(hash),Instant.now().plusSeconds(1200));var state=packets.findSource(MemoryMapper.identity("t1"),MemoryMapper.identity(source));
        var direct=new MemoryContextPacket.Dependency(state.sourceType(),source,hash,state.grantEpoch(),state.sourceEpoch(),state.deletionEpoch());
        dependencies.record(scope,"MESSAGE",user,hash,run,List.of(direct),List.of(List.of(direct)),List.of());var all=new ArrayList<>(preference);all.add(direct);dependencies.record(scope,"MESSAGE",assistant,"1",run,all,List.of(all),List.of());
    }
}
