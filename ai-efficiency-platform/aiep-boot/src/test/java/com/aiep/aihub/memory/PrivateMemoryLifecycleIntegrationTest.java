package com.aiep.aihub.memory;

import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.application.operation.OperationAssistantService;
import com.aiep.aihub.facade.memory.DefaultMemoryFacade;
import com.aiep.aihub.repository.memory.*;
import com.aiep.aihub.repository.operation.*;
import com.aiep.aihub.web.memory.*;
import com.aiep.aihub.web.operation.OperationAssistantController;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformai.agent.*;
import com.aiep.platformai.api.AiInvokeFacade;
import com.aiep.platformai.facade.AiInvokeFacadeImpl;
import com.aiep.platformcore.config.TraceIdFilter;
import com.baomidou.mybatisplus.autoconfigure.MybatisPlusAutoConfiguration;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.fasterxml.jackson.databind.*;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.sql.*;
import java.time.*;
import java.util.*;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.web.reactive.function.client.WebClient;
import static org.junit.jupiter.api.Assertions.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;

/** 本机生产MVC→Service/Mapper→真实Agent HTTP→Controller→Fake模型边界；不使用共享配置。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class PrivateMemoryLifecycleIntegrationTest {
    static final ObjectMapper JSON = new ObjectMapper().findAndRegisterModules();
    static final HttpClient HTTP = HttpClient.newHttpClient();
    static String javaBase;
    static String agentBase;
    static String secret;
    @Configuration(proxyBeanMethods=false)
    @EnableAutoConfiguration(exclude={DataSourceAutoConfiguration.class,MybatisPlusAutoConfiguration.class},excludeName={"org.redisson.spring.starter.RedissonAutoConfigurationV2","org.springframework.boot.autoconfigure.data.redis.RedisAutoConfiguration","org.springframework.boot.autoconfigure.data.redis.RedisRepositoriesAutoConfiguration"})
    @EnableTransactionManagement
    @Import({ConversationScopeResolver.class,MemoryScopePolicy.class,MemorySessionBindingService.class,MemoryPolicyService.class,
        MemoryVersionService.class,MemoryPreferenceService.class,DefaultMemoryFacade.class,MemoryActorResolver.class,MemoryController.class,
        MemoryExceptionHandler.class,MemoryForgetService.class,MemorySuppressionService.class,MemoryDeletionService.class,MemorySourceInvalidationService.class,MemoryDeletionController.class,MemoryDeletionExceptionHandler.class,MemoryDeletionLease.class,MemoryDeletionDispatcher.class,MemoryCleanupAckAdapter.class,MemoryLocalCleanupProof.class,MemoryPacketService.class,MemoryDependencyService.class,MemoryHistoryProjection.class,
        OperationAssistantService.class,OperationAssistantController.class,TraceIdFilter.class,SafeBoundaryDiagnostics.class,
        com.aiep.aihub.application.customer.CustomerServiceApplicationService.class,
        com.aiep.aihub.application.customer.CustomerServicePendingRunCreator.class,
        com.aiep.aihub.application.customer.CustomerServiceEventProjector.class,
        com.aiep.aihub.web.customer.CustomerServiceController.class})
    static class ITConfiguration {
        @Bean DataSource dataSource(){return new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));}
        @Bean PlatformTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
        @Bean SqlSessionFactory sqlSessionFactory(DataSource ds)throws Exception {
            var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
            factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryForgetMapper.xml"),new ClassPathResource("mapper/memory/MemoryLifecycleMapper.xml"),new ClassPathResource("mapper/memory/MemoryPacketMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
            var configuration=new com.baomidou.mybatisplus.core.MybatisConfiguration();configuration.setMapUnderscoreToCamelCase(true);
            for(var type:List.of(OperationConversationMapper.class,OperationMessageMapper.class,OperationRunMapper.class,OperationArtifactMapper.class))configuration.addMapper(type);
            factory.setConfiguration(configuration);return factory.getObject();
        }
        @Bean MemoryForgetMapper forgetMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryForgetMapper.class);}
        @Bean MemoryLifecycleMapper lifecycleMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryLifecycleMapper.class);}
        @Bean MemoryMapper memoryMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryMapper.class);}
        @Bean MemoryPacketMapper packetMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(MemoryPacketMapper.class);}
        @Bean IdentitySessionMapper identityMapper(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(IdentitySessionMapper.class);}
        @Bean IdentityFacade identity(IdentitySessionMapper m){return new DatabaseIdentityFacade(m);}
        @Bean com.aiep.aihub.repository.customer.CustomerServiceMappers customer(DataSource ds){return new com.aiep.aihub.repository.customer.JdbcCustomerServiceMappers(new org.springframework.jdbc.core.JdbcTemplate(ds));}
        @Bean com.aiep.aihub.repository.management.AiManagementMappers management(DataSource ds){return new com.aiep.aihub.repository.management.JdbcAiManagementMappers(new org.springframework.jdbc.core.JdbcTemplate(ds));}
        @Bean OperationConversationMapper conversations(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(OperationConversationMapper.class);}
        @Bean OperationMessageMapper messages(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(OperationMessageMapper.class);}
        @Bean OperationRunMapper runs(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(OperationRunMapper.class);}
        @Bean OperationArtifactMapper artifacts(SqlSessionFactory f){return new SqlSessionTemplate(f).getMapper(OperationArtifactMapper.class);}
        @Bean MemoryValueCodec codec(){return new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));}
        @Bean AiInvokeFacade ai(){var props=new AgentClientProperties();props.setBaseUrl(agentBase);props.setInternalSecret(secret);
            return new AiInvokeFacadeImpl(new HttpAgentClient(props,WebClient.builder(),JSON),new HttpCustomerServiceAgentClient(props,WebClient.builder(),JSON));}
    }
    @org.springframework.web.bind.annotation.RestControllerAdvice(assignableTypes={OperationAssistantController.class,com.aiep.aihub.web.customer.CustomerServiceController.class})
    static class SafeBoundaryDiagnostics {
        @org.springframework.web.bind.annotation.ExceptionHandler(org.springframework.dao.DataAccessException.class)
        org.springframework.http.ResponseEntity<Map<String,Object>> storage(org.springframework.dao.DataAccessException failure) {
            Throwable current=failure;String state="unknown";int vendor=0;
            while(current!=null){if(current instanceof SQLException sql){state=sql.getSQLState();vendor=sql.getErrorCode();break;}current=current.getCause();}
            System.out.println("D13 boundary=java_storage SQLState="+state+" vendor="+vendor);
            return org.springframework.http.ResponseEntity.status(503).body(Map.of("code","MEMORY_STORAGE_UNAVAILABLE"));
        }
        @org.springframework.web.bind.annotation.ExceptionHandler(AgentTransportException.class)
        org.springframework.http.ResponseEntity<Map<String,Object>> transport(AgentTransportException failure) {
            System.out.println("D13 boundary=agent_transport status="+failure.getStatusCode()+" code="+failure.getErrorCode());
            return org.springframework.http.ResponseEntity.status(failure.getStatusCode()).body(Map.of("code",failure.getErrorCode()));
        }
        @org.springframework.web.bind.annotation.ExceptionHandler(com.aiep.aihub.api.memory.MemoryContracts.MemoryException.class)
        org.springframework.http.ResponseEntity<Map<String,Object>> memory(com.aiep.aihub.api.memory.MemoryContracts.MemoryException failure) {
            System.out.println("D13 boundary=java_memory code="+failure.code());
            return org.springframework.http.ResponseEntity.status(409).body(Map.of("code",failure.code()));
        }
    }

    @Test void savedPreferencesReachActualOperationRequestsAndPersistentRunManifests()throws Exception {
        var url=URI.create(required("MEMORY_IT_MYSQL_JDBC_URL").substring(5));
        assertEquals("127.0.0.1",url.getHost());assertTrue(url.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(required("MEMORY_IT_MYSQL_JDBC_URL"),required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
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
        secret=required("MEMORY_IT_INTERNAL_SECRET");int port=Integer.parseInt(required("MEMORY_IT_AGENT_PORT"));agentBase="http://127.0.0.1:"+port;
        var root=Path.of("../..").toAbsolutePath().normalize();
        var process=new ProcessBuilder(root.resolve("efficiency-platform-agent/.venv/Scripts/python.exe").toString(),"-m","tests.integration.context_control.private_memory_http_fixture")
            .directory(root.resolve("efficiency-platform-agent").toFile()).redirectErrorStream(true)
            .redirectOutput(root.resolve(".local-acceptance/agent-memory-implementation/logs/D17J-agent-http.log").toFile()).start();
        try {
            boolean ready=false;
            long readinessDeadline=System.nanoTime()+Duration.ofSeconds(30).toNanos();
            var readinessClient=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build();
            while(System.nanoTime()<readinessDeadline) {
                if(!process.isAlive())throw new AssertionError("隔离Agent进程退出，检查安全fixture日志");
                try {ready=readinessClient.send(HttpRequest.newBuilder(URI.create(agentBase+"/health/live")).timeout(Duration.ofSeconds(1)).GET().build(),HttpResponse.BodyHandlers.discarding()).statusCode()==200;}catch(java.io.IOException unavailable){}
                if(ready)break;Thread.sleep(100);
            }
            assertTrue(ready,"隔离Agent启动超时");
            var app=new SpringApplication(ITConfiguration.class);
            app.setDefaultProperties(Map.of("spring.config.location","optional:classpath:/memory-it-no-shared-config/","server.address","127.0.0.1","server.port","0","spring.main.banner-mode","off","logging.level.root","ERROR","spring.jmx.enabled","false","aiep.memory.packet-enabled","true","aiep.memory.deletion-worker-enabled","true"));
            try(var context=(ServletWebServerApplicationContext)app.run("--spring.config.location=optional:classpath:/memory-it-no-shared-config/")) {
                javaBase="http://127.0.0.1:"+context.getWebServer().getPort();
                String credential=TOKENS.get("t1:u1"),session1=SESSIONS.get("t1:u1:operations:1"),session2=SESSIONS.get("t1:u1:operations:2");
                var language=postJava("/api/aihub/memories",credential,command("operations",session1,"response.language","zh-CN",0,"d13-language"),200);
                var format=postJava("/api/aihub/memories",credential,command("operations",session1,"response.format","bullets",0,"d13-format"),200);
                var submittedRuns=new ArrayList<String>();
                for(int i=0;i<2;i++) {
                    String session=i==0?session1:session2;
                    var result=postJava("/api/operations/conversations/"+session+"/messages",credential,JSON.writeValueAsString(Map.of("message","d13-history-first-"+i+"解释一种常见概念","clientRequestId","d13-run-"+i)),202);
                    assertFalse(result.path("data").path("runId").asText().isBlank());
                    submittedRuns.add(result.path("data").path("runId").asText());
                }
                var proof=proof();assertEquals("FIXED_FAKE",proof.path("provider_mode").asText());
                assertEquals(2,proof.path("runs").size());
                for(var run:proof.path("runs")){assertEquals("succeeded",run.path("status").asText(),"运行失败稳定码="+run.path("failure_code").asText());assertTrue(run.path("encrypted").asBoolean());}
                int directs=0;
                for(var request:proof.path("requests"))if("direct".equals(request.path("node_id").asText())){directs++;assertEquals(2,request.path("preference_count").asInt());assertFalse(request.path("legacy_present").asBoolean());}
                assertEquals(2,directs);
                for(String runId:submittedRuns) {
                    var sse=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/operations/runs/"+runId+"/events")).header("Authorization","Bearer "+credential)
                        .timeout(Duration.ofSeconds(15)).GET().build(),HttpResponse.BodyHandlers.ofString());
                    assertEquals(200,sse.statusCode());assertTrue(sse.body().contains("synthetic display result"));
                }
                try(var c=ds.getConnection();var s=c.prepareStatement("INSERT INTO ai_operation_message(id,conversation_id,tenant_id,role,content,run_id,created_at) VALUES(?,?,'t1','assistant','legacy-unsafe-marker',?,UTC_TIMESTAMP(6))")) {
                    s.setString(1,UUID.randomUUID().toString());s.setString(2,session1);s.setString(3,submittedRuns.get(0));assertEquals(1,s.executeUpdate());
                }
                var follow=postJava("/api/operations/conversations/"+session1+"/messages",credential,JSON.writeValueAsString(Map.of("message","d13-history-follow-up按刚才继续","clientRequestId","d13-follow")),202);
                String followRun=follow.path("data").path("runId").asText();
                var followProof=proof();assertHistory(followProof,followRun,"direct",true,"d13-history-first-0",true);
                assertHistory(followProof,followRun,"intent",true,"d13-history-first-0",true);
                assertHistory(followProof,followRun,"direct",true,"d13-history-first-1",false);
                for(var manifest:followProof.path("manifests"))if(followRun.equals(manifest.path("scope").path("execution_id").asText())&&"intent".equals(manifest.path("node_id").asText()))assertEquals(4,manifest.path("safety_dependencies").size());
                var followStream=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/operations/runs/"+followRun+"/events")).header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(15)).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(200,followStream.statusCode());
                String originalInputSource;
                try(var c=ds.getConnection();var s=c.prepareStatement("SELECT CONVERT(d.source_id USING utf8mb4) FROM ai_memory_dependency d JOIN ai_operation_run r ON CAST(r.user_message_id AS BINARY)=d.target_id WHERE d.tenant_id='t1' AND d.target_type='MESSAGE' AND r.id=?")) {
                    s.setString(1,submittedRuns.get(0));try(var rows=s.executeQuery()){assertTrue(rows.next());originalInputSource=rows.getString(1);}
                }
                try(var c=ds.getConnection();var s=c.prepareStatement("UPDATE ai_memory_source SET source_epoch=source_epoch+1 WHERE tenant_id='t1' AND id=?")){s.setBytes(1,originalInputSource.getBytes());assertEquals(1,s.executeUpdate());}
                var third=postJava("/api/operations/conversations/"+session1+"/messages",credential,JSON.writeValueAsString(Map.of("message","继续处理独立输入","clientRequestId","d13-third")),202);
                var historyProof=proof();String thirdRun=third.path("data").path("runId").asText();
                assertHistory(historyProof,thirdRun,"direct",false,"d13-history-first-0",false);
                assertHistory(historyProof,thirdRun,"direct",false,"d13-history-follow-up",true);
                String revokedSource;
                try(var c=ds.getConnection();var s=c.prepareStatement("SELECT CONVERT(d.source_id USING utf8mb4) FROM ai_memory_dependency d WHERE d.tenant_id='t1' AND d.target_type='MEMORY_VERSION' AND d.target_id=? AND d.target_version=?")) {
                    s.setBytes(1,language.path("data").path("id").asText().getBytes());s.setBytes(2,language.path("data").path("versionId").asText().getBytes());
                    try(var rows=s.executeQuery()){assertTrue(rows.next());revokedSource=rows.getString(1);}
                }
                var scope=new com.aiep.aihub.api.memory.MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",session2);
                var projection=context.getBean(MemoryHistoryProjection.class);
                List<MemoryHistoryProjection.Message> answers;
                try(var c=ds.getConnection();var s=c.prepareStatement("SELECT id,content FROM ai_operation_message WHERE run_id=? AND role='assistant'")) {
                    s.setString(1,submittedRuns.get(1));try(var rows=s.executeQuery()){assertTrue(rows.next());answers=List.of(new MemoryHistoryProjection.Message(scope,rows.getString(1),"1","assistant",rows.getString(2)));}
                }
                assertEquals(1,projection.select(scope,answers).size());
                var dep=context.getBean(MemoryDependencyService.class);
                assertEquals(3,dep.dependencies(scope,"MESSAGE",answers.get(0).id(),"1").size());
                try(var c=ds.getConnection();var s=c.prepareStatement("UPDATE ai_memory_source SET source_epoch=source_epoch+1 WHERE tenant_id='t1' AND id=?")) {s.setBytes(1,revokedSource.getBytes());assertEquals(1,s.executeUpdate());}
                assertTrue(projection.select(scope,answers).isEmpty());
                String stoppedExecution=submittedRuns.get(0),eventId=UUID.randomUUID().toString();
                String invalidation=JSON.writeValueAsString(Map.of("event_id",eventId,"expected_execution_revision",1,"grant_epoch",0,"source_epoch",1,"deletion_epoch",0));
                var stopped=HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/internal/v1/memory/executions/"+stoppedExecution+"/invalidate"))
                    .header("Authorization","Bearer "+secret).header("X-Tenant-ID","t1").header("Content-Type","application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(invalidation)).build(),HttpResponse.BodyHandlers.ofString());
                assertEquals(200,stopped.statusCode());assertEquals("AGENT_STOP",JSON.readTree(stopped.body()).path("target").asText());
                var deniedManifest=HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/internal/v1/memory/executions/"+stoppedExecution+"/manifest"))
                    .header("Authorization","Bearer "+secret).header("X-Tenant-ID","t1").GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(409,deniedManifest.statusCode());
                for(var manifest:proof.path("manifests")) {
                    assertEquals("window/1",manifest.path("policy_version").asText());assertFalse(manifest.path("packet_id").isNull());
                    if("direct".equals(manifest.path("node_id").asText()))assertEquals(3,manifest.path("safety_dependencies").size());
                }
                int count=proof().path("requests").size();
                for(int i=0;i<3;i++) {var response=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/aihub/memories?topAgent=operations&sessionId="+session2)).header("Authorization","Bearer "+credential).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(200,response.statusCode());}
                assertEquals(count,proof().path("requests").size());
                var replay=postJava("/api/operations/conversations/"+session1+"/messages",credential,JSON.writeValueAsString(Map.of("message","d13-history-first-0解释一种常见概念","clientRequestId","d13-run-0")),202);
                assertEquals(count,proof().path("requests").size());
                try(var c=ds.getConnection();var s=c.createStatement();var rows=s.executeQuery("SELECT COUNT(*) FROM ai_memory_packet WHERE references_json LIKE '%zh-CN%' OR references_json LIKE '%bullets%'")) {assertTrue(rows.next());assertEquals(0,rows.getInt(1));}
                var customerRunIds=new ArrayList<String>();
                for(String user:List.of("u1","u2")) {
                    String token=TOKENS.get("t1:"+user),firstSession=SESSIONS.get("t1:"+user+":customer-service:1");
                    postJava("/api/aihub/memories",token,command("customer-service",firstSession,"response.format","table",0,"customer-format-"+user),200);
                    for(int i=1;i<=2;i++) {
                        String session=SESSIONS.get("t1:"+user+":customer-service:"+i);
                        var submitted=postJava("/api/customer-service/conversations/"+session+"/messages",token,
                            JSON.writeValueAsString(Map.of("contractVersion","customer-service-message/1","message","d13-csr-first-"+user+"提供一般工作建议","clientRequestId","csr-"+user+"-"+i)),200);
                        customerRunIds.add(submitted.path("data").path("runId").asText());
                    }
                }
                var customerProof=proof();assertEquals(4,customerProof.path("customer_runs").size());
                for(var run:customerProof.path("customer_runs"))assertEquals("SUCCEEDED",run.path("status").asText());
                int customerAnswers=0;
                for(var request:customerProof.path("requests"))if("customer-service:answer_general".equals(request.path("node_id").asText())) {customerAnswers++;assertEquals(1,request.path("preference_count").asInt());}
                assertEquals(4,customerAnswers);
                for(var request:customerProof.path("requests"))if("customer-service:intent".equals(request.path("node_id").asText()))assertEquals(0,request.path("preference_count").asInt());
                String csrSession=SESSIONS.get("t1:u1:customer-service:1"),csrRun=customerRunIds.get(0);
                var csrStream=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/customer-service/runs/"+csrRun+"/events")).header("Authorization","Bearer "+credential).timeout(Duration.ofSeconds(15)).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(200,csrStream.statusCode());
                var csrFollow=postJava("/api/customer-service/conversations/"+csrSession+"/messages",credential,JSON.writeValueAsString(Map.of("contractVersion","customer-service-message/1","message","继续刚才的一般建议","clientRequestId","csr-follow")),200);
                var csrHistory=proof();String csrFollowRun=csrFollow.path("data").path("runId").asText();
                assertHistory(csrHistory,csrFollowRun,"customer-service:intent",true,"d13-csr-first-u1",true);
                assertHistory(csrHistory,csrFollowRun,"customer-service:answer_general",true,"d13-csr-first-u1",true);
                assertHistory(csrHistory,csrFollowRun,"customer-service:answer_general",true,"d13-csr-first-u2",false);
                try(var c=ds.getConnection();var s=c.prepareStatement("SELECT CONVERT(d.target_version USING utf8mb4),SHA2(CAST(m.content_markdown AS BINARY),256) FROM ai_memory_dependency d JOIN ai_customer_service_message m ON CAST(m.id AS BINARY)=d.target_id WHERE d.tenant_id='t1' AND d.target_type='MESSAGE' AND m.run_id=? AND m.role='USER'")) {
                    s.setString(1,csrRun);try(var rows=s.executeQuery()){assertTrue(rows.next());assertEquals(rows.getString(2),rows.getString(1));}
                }
                var denied=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/aihub/memories?topAgent=customer-service&sessionId="+SESSIONS.get("t1:u1:customer-service:1")))
                    .header("Authorization","Bearer "+TOKENS.get("t1:u2")).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(403,denied.statusCode());
                verifyActualWorkerDeletion(context,ds,credential,"operations","response.language","en-US");
                verifyActualWorkerDeletion(context,ds,credential,"customer-service","response.format","bullets");
                verifyNeverExecutedManagementMatrix(context,ds);
            }
        } finally {try{HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/__memory_it__/shutdown")).header("Authorization","Bearer "+secret).POST(HttpRequest.BodyPublishers.noBody()).build(),HttpResponse.BodyHandlers.discarding());process.waitFor(15,java.util.concurrent.TimeUnit.SECONDS);}catch(Exception ignored){}process.destroy();if(!process.waitFor(10,java.util.concurrent.TimeUnit.SECONDS))process.destroyForcibly();}
    }
    static void verifyActualWorkerDeletion(ServletWebServerApplicationContext context,DataSource ds,String credential,String domain,String field,String newValue)throws Exception {
        String item,version;long revision;
        try(var c=ds.getConnection();var q=c.prepareStatement("SELECT CONVERT(id USING utf8mb4),CONVERT(current_version_id USING utf8mb4),revision FROM ai_memory_item WHERE tenant_id='t1' AND owner_id='u1' AND domain=? AND field_key=? AND lifecycle='LIVE'")){q.setString(1,domain);q.setString(2,field);try(var rows=q.executeQuery()){assertTrue(rows.next());item=rows.getString(1);version=rows.getString(2);revision=rows.getLong(3);}}
        var technicalRuns=new ArrayList<String>();
        try(var c=ds.getConnection();var q=c.prepareStatement("SELECT DISTINCT CONVERT(e.runtime_id USING utf8mb4) FROM agent_memory_execution e JOIN ai_memory_dependency d ON d.tenant_id=e.tenant_id AND d.execution_id=e.execution_id JOIN ai_memory_dependency own ON own.tenant_id=d.tenant_id AND own.source_id=d.source_id AND own.target_type='MEMORY_VERSION' WHERE own.tenant_id='t1' AND own.target_id=? AND d.target_type='EXECUTION'")){q.setBytes(1,item.getBytes(java.nio.charset.StandardCharsets.UTF_8));try(var rows=q.executeQuery()){while(rows.next())technicalRuns.add(rows.getString(1));}}
        assertFalse(technicalRuns.isEmpty());
        if("operations".equals(domain))for(String run:technicalRuns)try(var c=ds.getConnection();var update=c.prepareStatement("UPDATE agent_run_event SET event_json=JSON_SET(event_json,'$.payload.d17_forget_marker','synthetic-forget-body-marker') WHERE tenant_id='t1' AND run_id=?")){update.setString(1,run);assertTrue(update.executeUpdate()>0);}
        int calls=proof().path("requests").size();
        var forgotten=postJava("/api/aihub/memory-deletions",credential,JSON.writeValueAsString(Map.of("topAgent",domain,"itemId",item,"expectedRevision",revision,"idempotencyKey","d17-real-forget-"+domain)),200).path("data");
        assertEquals("DELETE_PENDING",forgotten.path("status").asText());assertEquals(0,forgotten.path("completedTargets").asInt());
        String job=forgotten.path("jobId").asText();
        var lifecycle=context.getBean(MemoryLifecycleMapper.class);
        var due=lifecycle.due(16).stream().filter(value->job.equals(new String(value.jobId(),java.nio.charset.StandardCharsets.UTF_8))).findFirst().orElseThrow();
        new MemoryDeletionLease(ds).run(due,()->{
            var executor=java.util.concurrent.Executors.newSingleThreadExecutor();
            try{assertFalse(executor.submit(()->new MemoryDeletionLease(ds).run(due,()->fail("同job第二worker不得外发"))).get(3,java.util.concurrent.TimeUnit.SECONDS));}
            catch(Exception error){throw new AssertionError("实际两连接会话锁检查失败",error);}finally{executor.shutdownNow();}
        });
        assertEquals(1,lifecycle.claim(due,"simulated-crashed-lease".getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        try(var c=ds.getConnection();var update=c.prepareStatement("UPDATE ai_memory_outbox SET lease_until=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE tenant_id='t1' AND event_id=? AND status='CLAIMED'")){update.setBytes(1,job.getBytes(java.nio.charset.StandardCharsets.UTF_8));assertEquals(1,update.executeUpdate());}
        var dispatcher=context.getBean(MemoryDeletionDispatcher.class);dispatcher.dispatch();dispatcher.dispatch();
        var response=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+"/api/aihub/memory-deletions/"+job+"?topAgent="+domain)).header("Authorization","Bearer "+credential).GET().build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(200,response.statusCode());var done=JSON.readTree(response.body()).path("data");
        assertEquals("DELETED",done.path("status").asText(),"真实worker必须拿到Agent停止、PG整组清理、技术快照擦除及Java投影证据");
        assertEquals("SUCCEEDED",done.path("jobStatus").asText());assertEquals(6,done.path("completedTargets").asInt());
        MemoryForgetIntegrationTest.assertBody(ds,item,version,true);
        if("operations".equals(domain))for(String run:technicalRuns)try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM agent_run_event WHERE tenant_id='t1' AND run_id=? AND CAST(event_json AS CHAR) LIKE '%synthetic-forget-body-marker%'")){q.setString(1,run);try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals(0,rows.getInt(1),"技术event payload必须物理擦除而非只撤权");}}
        try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM agent_memory_execution e JOIN ai_memory_dependency d ON d.tenant_id=e.tenant_id AND d.execution_id=e.execution_id JOIN ai_memory_dependency own ON own.tenant_id=d.tenant_id AND own.source_id=d.source_id AND own.target_type='MEMORY_VERSION' WHERE own.tenant_id='t1' AND own.target_id=? AND d.target_type='EXECUTION' AND (e.state<>'SCRUBBED' OR e.snapshot_ciphertext IS NOT NULL OR e.snapshot_nonce IS NOT NULL)")){q.setBytes(1,item.getBytes(java.nio.charset.StandardCharsets.UTF_8));try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals(0,rows.getInt(1));}}
        assertEquals(calls,proof().path("requests").size(),"遗忘/重复队列不能增加Provider调用");
        var granted=postJava("/api/aihub/memory-suppressions/"+forgotten.path("suppressionId").asText()+"/reauthorizations",credential,JSON.writeValueAsString(Map.of("topAgent",domain,"itemId",item,"fieldKey",field,"value",newValue,"expectedRevision",done.path("revision").asLong(),"expected_suppression_revision",forgotten.path("suppressionRevision").asLong(),"idempotencyKey","d17-new-authorization-"+domain,"confirmation","ALLOW_REMEMBER")),200).path("data");
        assertNotEquals(version,granted.path("versionId").asText());MemoryForgetIntegrationTest.assertBody(ds,item,version,true);
    }
    static void verifyNeverExecutedManagementMatrix(ServletWebServerApplicationContext context,DataSource ds)throws Exception {
        int providerCalls=proof().path("requests").size(),scopes=0;
        for(String tenant:List.of("t1","t2"))for(String user:List.of("u1","u2"))for(String domain:List.of("operations","customer-service")){
            String scope=tenant+":"+user+":"+domain,credential=TOKENS.get(tenant+":"+user);
            String first=SESSIONS.get(scope+":1"),second=SESSIONS.get(scope+":2");
            String field="response.detail_level",key="d17-matrix-"+scope;
            try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_item WHERE tenant_id=? AND owner_id=? AND domain=? AND field_key=?")){
                q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity(user));q.setString(3,domain);q.setString(4,field);
                try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals(0,rows.getInt(1),"矩阵字段必须经真实DB确认尚未使用");}
            }
            var saved=postJava("/api/aihub/memories",credential,command(domain,first,field,"concise",0,key+"-save"),200).path("data");
            String item=saved.path("id").asText(),oldVersion=saved.path("versionId").asText();
            var fromOtherSession=getJava("/api/aihub/memories/"+item+"?topAgent="+domain+"&sessionId="+second,credential,200).path("data").path("preference");
            assertEquals(item,fromOtherSession.path("id").asText());assertEquals(oldVersion,fromOtherSession.path("versionId").asText());assertEquals("concise",fromOtherSession.path("value").asText());
            String otherTenant=tenant.equals("t1")?"t2":"t1",otherUser=user.equals("u1")?"u2":"u1",otherAgent=domain.equals("operations")?"customer-service":"operations";
            getJava("/api/aihub/memories/"+item+"?topAgent="+domain+"&sessionId="+SESSIONS.get(otherTenant+":"+user+":"+domain+":1"),TOKENS.get(otherTenant+":"+user),404);
            getJava("/api/aihub/memories/"+item+"?topAgent="+domain+"&sessionId="+SESSIONS.get(tenant+":"+otherUser+":"+domain+":1"),TOKENS.get(tenant+":"+otherUser),404);
            getJava("/api/aihub/memories/"+item+"?topAgent="+otherAgent+"&sessionId="+SESSIONS.get(tenant+":"+user+":"+otherAgent+":1"),credential,404);
            var corrected=postJava("/api/aihub/memories/"+item+"/corrections",credential,command(domain,second,field,"detailed",saved.path("revision").asLong(),key+"-correct"),200).path("data");
            assertNotEquals(oldVersion,corrected.path("versionId").asText());assertEquals(saved.path("revision").asLong()+1,corrected.path("revision").asLong());
            for(String session:List.of(first,second)){
                var current=getJava("/api/aihub/memories/"+item+"?topAgent="+domain+"&sessionId="+session,credential,200).path("data").path("preference");
                assertEquals("detailed",current.path("value").asText());assertEquals(corrected.path("versionId"),current.path("versionId"));
            }
            try(var c=ds.getConnection();var q=c.prepareStatement("SELECT status FROM ai_memory_version WHERE tenant_id=? AND item_id=? AND id=?")){
                q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity(item));q.setBytes(3,MemoryMapper.identity(oldVersion));
                try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals("SUPERSEDED",rows.getString(1));}
            }
            try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_dependency d JOIN ai_memory_dependency own ON own.tenant_id=d.tenant_id AND own.source_id=d.source_id AND own.target_type='MEMORY_VERSION' WHERE own.tenant_id=? AND own.target_id=? AND (d.target_type<>'MEMORY_VERSION' OR d.execution_id IS NOT NULL OR d.root_thread_ref IS NOT NULL OR d.child_thread_ref IS NOT NULL OR d.checkpoint_namespace IS NOT NULL)")){
                q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity(item));try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals(0,rows.getInt(1),"必须用真实完整来源闭包证明该item从未进入任何执行或线程");}
            }
            var forgotten=postJava("/api/aihub/memory-deletions",credential,JSON.writeValueAsString(Map.of("topAgent",domain,"sessionId",first,"itemId",item,"expectedRevision",corrected.path("revision").asLong(),"idempotencyKey",key+"-forget")),200).path("data");
            assertEquals("DELETE_PENDING",forgotten.path("status").asText());assertEquals(0,forgotten.path("completedTargets").asInt());
            context.getBean(MemoryDeletionDispatcher.class).dispatch();
            var done=getJava("/api/aihub/memory-deletions/"+forgotten.path("jobId").asText()+"?topAgent="+domain+"&sessionId="+second,credential,200).path("data");
            assertEquals("DELETED",done.path("status").asText(),"真实NO_EXECUTION来源闭包应完成CPU遗忘");assertEquals("SUCCEEDED",done.path("jobStatus").asText());assertEquals(6,done.path("completedTargets").asInt());
            for(String session:List.of(first,second))getJava("/api/aihub/memories/"+item+"?topAgent="+domain+"&sessionId="+session,credential,404);
            var suppressed=postJava("/api/aihub/memories",credential,command(domain,second,field,"concise",done.path("revision").asLong(),key+"-ordinary-relearn"),422);
            assertEquals("FEATURE_DISABLED",suppressed.path("code").asText());
            try(var c=ds.getConnection();var q=c.prepareStatement("SELECT COUNT(*) FROM ai_memory_suppression WHERE tenant_id=? AND id=? AND suppression_kind='FIELD' AND active=TRUE")){
                q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity(forgotten.path("suppressionId").asText()));
                try(var rows=q.executeQuery()){assertTrue(rows.next());assertEquals(1,rows.getInt(1),"原字段抑制必须仍然有效");}
            }
            try(var c=ds.getConnection();var q=c.prepareStatement("SELECT status,encrypted_payload,nonce,auth_tag,content_hmac FROM ai_memory_version WHERE tenant_id=? AND item_id=?")){
                q.setBytes(1,MemoryMapper.identity(tenant));q.setBytes(2,MemoryMapper.identity(item));int versions=0;
                try(var rows=q.executeQuery()){while(rows.next()){versions++;assertEquals("DELETED",rows.getString(1));for(int column=2;column<=5;column++)assertNull(rows.getBytes(column));}}assertEquals(2,versions);
            }
            scopes++;
        }
        assertEquals(8,scopes);assertEquals(providerCalls,proof().path("requests").size(),"8范围管理/清理不能产生任何Provider调用");
        System.out.println("D17 managementMatrix scopes=8 sessions=16 sourceClosureNoExecution=true atomicBodiesScrubbed=true providerCallsUnchanged=true");
    }
    static JsonNode getJava(String path,String credential,int expected)throws Exception {
        var result=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+path)).header("Authorization","Bearer "+credential).GET().build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(expected,result.statusCode(),"生产HTTP GET状态不符，禁止在断言输出正文");return JSON.readTree(result.body());
    }
    static JsonNode postJava(String path,String credential,String body,int expected)throws Exception {
        var result=HTTP.send(HttpRequest.newBuilder(URI.create(javaBase+path)).header("Authorization","Bearer "+credential).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build(),HttpResponse.BodyHandlers.ofString());
        assertEquals(expected,result.statusCode(),"生产HTTP状态不符，响应仅在本机安全handler诊断");return JSON.readTree(result.body());
    }
    static JsonNode proof()throws Exception {var result=HTTP.send(HttpRequest.newBuilder(URI.create(agentBase+"/__memory_it__/proof")).header("Authorization","Bearer "+secret).GET().build(),HttpResponse.BodyHandlers.ofString());assertEquals(200,result.statusCode());return JSON.readTree(result.body());}
    static void assertHistory(JsonNode proof,String execution,String node,boolean answer,String marker,boolean present) {
        boolean seen=false;
        for(var request:proof.path("requests"))if(execution.equals(request.path("execution_id").asText())&&node.equals(request.path("node_id").asText())) {
            seen=true;assertEquals(answer,request.path("prior_answer_present").asBoolean());
            boolean found=false;for(var value:request.path("history_markers"))if(marker.equals(value.asText()))found=true;
            assertEquals(present,found);assertFalse(request.path("legacy_present").asBoolean());
        }
        assertTrue(seen,"必须核实际最终Provider请求");
    }
}
