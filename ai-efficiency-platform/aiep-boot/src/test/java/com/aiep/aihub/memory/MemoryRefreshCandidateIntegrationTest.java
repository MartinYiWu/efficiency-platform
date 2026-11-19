package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformai.api.dto.*;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** 真实MySQL候选锁与内部HTTP合成边界；不冒充PG/Graph/Provider验收。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshCandidateIntegrationTest {
    static final ObjectMapper JSON=new ObjectMapper();
    static byte[] b(String text){return MemoryMapper.identity(text);}

    @Test void confirmedExpiryAdvancesOnlyTheServerCandidateAndUnknownHttpReplaysIt()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            for(String table:List.of("ai_customer_service_conversation","ai_customer_service_message"))sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql",table);
            for(String table:List.of("id_hr_session","id_hr_grant"))sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql",table);
            seed(c);
            for(String domain:List.of("operations","customer-service")) {
                String raw;
                try(var q=c.prepareStatement("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id=? AND version_id='v1'")) {
                    q.setBytes(1,b("policy-"+domain));try(var r=q.executeQuery()){assertTrue(r.next());raw=r.getString(1);}
                }
                var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
                policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,
                    "sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),
                    "executionGrants",List.of(Map.of("node_id","direct","execution_agent_id",domain,"purpose","assistant_response")))));
                try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1',?,'refresh-scope-it',?,?)")) {
                    q.setBytes(1,b("policy-"+domain));q.setString(2,policy.toString());q.setBytes(3,random(32));assertEquals(1,q.executeUpdate());
                }
                try(var q=c.prepareStatement("UPDATE ai_memory_policy SET current_version_id='refresh-scope-it' WHERE tenant_id='t1' AND id=?")) {
                    q.setBytes(1,b("policy-"+domain));assertEquals(1,q.executeUpdate());
                }
            }
        }
        var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
        factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryPacketMapper.xml"),new ClassPathResource("mapper/memory/MemoryRefreshMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
        var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);
        var sql=new SqlSessionTemplate(factory.getObject());var memory=sql.getMapper(MemoryMapper.class);var packets=sql.getMapper(MemoryPacketMapper.class);var refresh=sql.getMapper(MemoryRefreshMapper.class);
        IdentityFacade identity=new DatabaseIdentityFacade(sql.getMapper(IdentitySessionMapper.class));
        var actor=identity.authenticate(TOKENS.get("t1:u1")).orElseThrow();
        var scopes=new MemoryScopePolicy(identity,null);var bindings=new MemorySessionBindingService(memory,scopes,new ConversationScopeResolver());
        var tx=new DataSourceTransactionManager(ds);var policies=new MemoryPolicyService(memory);
        var codec=new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));
        var preferences=new MemoryPreferenceService(memory,scopes,bindings,policies,new MemoryVersionService(memory,codec),codec,tx);
        var seconds=new AtomicLong(Instant.now().getEpochSecond());
        var clock=new Clock(){public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId zone){return this;}public Instant instant(){return Instant.ofEpochSecond(seconds.get());}};
        var service=new MemoryPacketService(true,memory,packets,scopes,bindings,policies,preferences,new MemoryDependencyService(packets,clock),codec,tx,clock,true,refresh,identity);
        try(var agent=new SyntheticAgentBoundary()) {
            var properties=new com.aiep.platformai.agent.AgentClientProperties();properties.setBaseUrl("http://127.0.0.1:"+agent.server.getAddress().getPort());properties.setInternalSecret(SyntheticAgentBoundary.SECRET);
            var ai=new com.aiep.platformai.facade.AiInvokeFacadeImpl(new com.aiep.platformai.agent.HttpAgentClient(properties,org.springframework.web.reactive.function.client.WebClient.builder(),JSON),new com.aiep.platformai.agent.HttpCustomerServiceAgentClient(properties,org.springframework.web.reactive.function.client.WebClient.builder(),JSON));
            var resumes=new MemoryContextResumeService(scopes,bindings,packets,ai,service);
            for(String domain:List.of("operations","customer-service")) {
                String table=domain.equals("operations")?"ai_operation_message":"ai_customer_service_message",column=domain.equals("operations")?"content":"content_markdown";
                String session=SESSIONS.get("t1:u1:"+domain+":1"),message=UUID.randomUUID().toString(),execution="candidate-"+domain;
                var scope=new MemoryScopeDTO("t1","u1",domain,domain,"CONVERSATION",session);
                try(var c=ds.getConnection();var q=c.prepareStatement("INSERT INTO "+table+"(id,conversation_id,tenant_id,role,"+column+",created_at) VALUES(?,?,'t1','user','synthetic-candidate-input',UTC_TIMESTAMP(6))")){q.setString(1,message);q.setString(2,session);assertEquals(1,q.executeUpdate());}
                String sourceId="source-"+domain,digest=hash("synthetic-candidate-input");
                assertEquals(1,packets.insertInputSource(b("t1"),b(sourceId),b(message),b(digest),clock.instant().plusSeconds(900)));
                var source=packets.findSource(b("t1"),b(sourceId));assertNotNull(source);
                var direct=new MemoryContextPacket.Dependency(source.sourceType(),sourceId,digest,source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch());
                var original=service.issue(actor,scope,execution,execution,JSON.readTree("{\"message\":\"synthetic-candidate-input\"}"),seconds.get()+300,List.of(direct));
                new org.springframework.transaction.support.TransactionTemplate(tx).execute(status->{
                    assertArrayEquals(b(execution),refresh.lockPacket(b("t1"),b(execution)).executionId());
                    var probe=java.util.concurrent.Executors.newSingleThreadExecutor();
                    try {
                        var blocked=probe.submit(()->{
                            try(var c=ds.getConnection()) {
                                c.setAutoCommit(false);
                                try {
                                    try(var command=c.createStatement()){command.execute("SET SESSION innodb_lock_wait_timeout=1");}
                                    try(var q=c.prepareStatement("SELECT execution_id FROM ai_memory_packet WHERE tenant_id=? AND execution_id=? FOR UPDATE")) {
                                        q.setBytes(1,b("t1"));q.setBytes(2,b(execution));try(var r=q.executeQuery()){assertTrue(r.next());return false;}
                                    }
                                }catch(java.sql.SQLException locked){assertEquals(1205,locked.getErrorCode());return true;}
                                finally{c.rollback();}
                            }
                        });
                        assertTrue(blocked.get(5,java.util.concurrent.TimeUnit.SECONDS));
                    }catch(Exception failure){throw new AssertionError("original packet X lock must remain held until transaction commit",failure);}
                    finally{probe.shutdownNow();}
                    return null;
                });
                seconds.addAndGet(61);var wait=MemoryRefreshIntegrationTest.wait(original,1,"wait-"+domain,"a".repeat(64),0);agent.begin(wait);
                assertThrows(com.aiep.platformai.agent.AgentTransportException.class,()->resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()));
                var first=refresh.findPending(b("t1"),b(execution));assertNotNull(first);
                assertEquals("MEMORY_REFRESH_PENDING",resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).code());
                assertEquals(agent.bodies.get(0),agent.bodies.get(1));assertEquals(1,refresh.countForWait(b("t1"),b(execution),b(wait.waitEventId())));
                seconds.addAndGet(61);agent.expire=true;
                assertEquals(MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED,resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).candidatePhase());
                assertEquals("EXPIRED_UNAPPLIED",refresh.findCandidate(b("t1"),b(execution),first.resumeRequestId()).phase());
                agent.expire=false;
                assertEquals("MEMORY_REFRESH_PENDING",resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).code());
                var second=refresh.findPending(b("t1"),b(execution));assertNotNull(second);assertFalse(Arrays.equals(first.resumeRequestId(),second.resumeRequestId()));assertTrue(second.targetRevision()>first.targetRevision());
                var pool=java.util.concurrent.Executors.newFixedThreadPool(2);
                try {
                    var a1=pool.submit(()->resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()));
                    var a2=pool.submit(()->resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()));
                    assertEquals("MEMORY_REFRESH_PENDING",a1.get(10,java.util.concurrent.TimeUnit.SECONDS).code());assertEquals("MEMORY_REFRESH_PENDING",a2.get(10,java.util.concurrent.TimeUnit.SECONDS).code());
                }finally{pool.shutdownNow();}
                assertEquals(2,refresh.countForWait(b("t1"),b(execution),b(wait.waitEventId())));assertEquals(agent.bodies.get(3),agent.bodies.get(4));assertEquals(agent.bodies.get(4),agent.bodies.get(5));
                assertEquals(second.requestHash(),refresh.findPending(b("t1"),b(execution)).requestHash());
                seconds.addAndGet(61);agent.expire=true;assertEquals(MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED,resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).candidatePhase());
                agent.expire=false;assertEquals("MEMORY_REFRESH_PENDING",resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).code());
                var third=refresh.findPending(b("t1"),b(execution));assertTrue(third.targetRevision()>second.targetRevision());
                seconds.addAndGet(61);agent.expire=true;assertEquals(MemoryResumeReceipt.State.BLOCKED,resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId()).state());
                int posts=agent.bodies.size();
                assertEquals("CONTEXT_REFRESH_LIMIT",assertThrows(MemoryContracts.MemoryException.class,()->resumes.onWaitEvent("t1",execution,wait.runtimeId(),wait.waitEventId())).code());
                assertEquals(posts,agent.bodies.size());assertEquals(3,refresh.countForWait(b("t1"),b(execution),b(wait.waitEventId())));assertNull(refresh.findPending(b("t1"),b(execution)));
                assertEquals(1,packets.findPacket(b("t1"),b(execution)).packetRevision());
                String carriedExecution=execution+"-carried";
                var carried=service.issue(actor,scope,carriedExecution,carriedExecution,JSON.readTree("{\"message\":\"synthetic-candidate-input\"}"),seconds.get()+300,List.of(direct));
                seconds.addAndGet(61);var carriedWait=MemoryRefreshIntegrationTest.wait(carried,1,"carried-"+domain,"b".repeat(64),2);
                agent.begin(carriedWait);agent.acceptedOffset=2;agent.first=false;
                assertEquals("MEMORY_REFRESH_PENDING",resumes.onWaitEvent("t1",carriedExecution,carriedWait.runtimeId(),carriedWait.waitEventId()).code());
                seconds.addAndGet(61);agent.expire=true;
                assertEquals(MemoryResumeReceipt.State.BLOCKED,resumes.onWaitEvent("t1",carriedExecution,carriedWait.runtimeId(),carriedWait.waitEventId()).state());
                assertEquals(1,refresh.countForWait(b("t1"),b(carriedExecution),b(carriedWait.waitEventId())));assertEquals(3,refresh.maxConfirmedCount(b("t1"),b(carriedExecution)));
                agent.waitCountOverride=2;int carriedPosts=agent.bodies.size();
                assertEquals("CONTEXT_REFRESH_LIMIT",assertThrows(MemoryContracts.MemoryException.class,()->resumes.onWaitEvent("t1",carriedExecution,carriedWait.runtimeId(),carriedWait.waitEventId())).code());
                assertEquals(carriedPosts,agent.bodies.size());assertEquals(1,refresh.countForWait(b("t1"),b(carriedExecution),b(carriedWait.waitEventId())));

            }
        }
        System.out.println("D16RF05E-fix realMySQL=passed domains=operations,customer-service httpUnknown=fixed pending=fixed unappliedExpiry=nextCandidate concurrentPrepared=one perWaitCandidates=3 fourth=denied staleWaitCount2Confirmed3=denied originalPacket=unchanged paidCalls=0");
    }
    static final class SyntheticAgentBoundary implements AutoCloseable {
        static final String SECRET="synthetic-candidate-http-secret-0000000000000000000";
        final com.sun.net.httpserver.HttpServer server;
        final java.util.concurrent.CopyOnWriteArrayList<String> bodies=new java.util.concurrent.CopyOnWriteArrayList<>();
        final Map<String,Integer> accepted=new LinkedHashMap<>();
        MemoryContextWait wait;boolean first=true;volatile boolean expire;volatile int acceptedOffset;volatile Integer waitCountOverride;
        SyntheticAgentBoundary()throws Exception {
            server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/",exchange->{try{respond(exchange);}finally{exchange.close();}});server.start();
        }
        synchronized void begin(MemoryContextWait next){wait=next;accepted.clear();bodies.clear();first=true;expire=false;acceptedOffset=0;waitCountOverride=null;}
        synchronized void respond(com.sun.net.httpserver.HttpExchange exchange)throws java.io.IOException {
            assertTrue(("Bearer "+SECRET).equals(exchange.getRequestHeaders().getFirst("Authorization")));assertEquals("t1",exchange.getRequestHeaders().getFirst("X-Tenant-ID"));
            byte[] response;int status;
            if(exchange.getRequestMethod().equals("GET")) {
                var w=wait;var current=new MemoryContextWait(w.contractVersion(),w.waitEventId(),w.runtimeId(),w.taskId(),w.executionId(),w.scope(),w.expectedPacketRevision(),w.expectedExecutionRevision(),w.expectedCurrentContextFingerprint(),w.operationHash(),w.logicalOperationId(),w.semanticInputHash(),w.canonicalRequestHmac(),w.attempt(),w.stageId(),w.stageSlot(),w.checkpointMode(),w.checkpointNs(),w.checkpointId(),w.waitPhase(),w.originalDeadline(),waitCountOverride==null?acceptedOffset+accepted.size():waitCountOverride);
                response=JSON.writeValueAsBytes(current);status=200;
            } else {
                String body=new String(exchange.getRequestBody().readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);bodies.add(body);
                var request=JSON.readValue(body,MemoryResumeRequest.class);int count=acceptedOffset+accepted.computeIfAbsent(request.resumeRequestId(),key->accepted.size()+1);
                if(first){first=false;exchange.sendResponseHeaders(500,-1);return;}
                var receipt=new MemoryResumeReceipt(expire?MemoryResumeReceipt.Code.MEMORY_REFRESH_PACKET_EXPIRED:MemoryResumeReceipt.Code.MEMORY_REFRESH_PENDING,"receipt-"+request.resumeRequestId(),request.waitEventId(),request.refreshedContext().packet().packetRevision(),request.expectedExecutionRevision(),request.packetRevision(),request.expectedCurrentContextFingerprint(),(long)count,expire?(count==3?MemoryResumeReceipt.State.BLOCKED:MemoryResumeReceipt.State.WAITING_CONTEXT):MemoryResumeReceipt.State.REFRESH_PENDING,expire?MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED:MemoryResumeReceipt.CandidatePhase.PENDING,null,false);
                response=JSON.writeValueAsBytes(receipt);status=receipt.resultCode().httpStatus();
            }
            exchange.getResponseHeaders().set("Content-Type","application/json");exchange.sendResponseHeaders(status,response.length);exchange.getResponseBody().write(response);
        }
        public void close(){server.stop(0);}
    }
}
