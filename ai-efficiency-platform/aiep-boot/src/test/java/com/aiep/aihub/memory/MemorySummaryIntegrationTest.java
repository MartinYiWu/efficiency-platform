package com.aiep.aihub.memory;

import com.aiep.aihub.api.memory.*;
import com.aiep.aihub.api.memory.MemorySummaryContracts.*;
import com.aiep.aihub.application.memory.*;
import com.aiep.aihub.application.memory.MemorySummarySourceService.*;
import com.aiep.aihub.repository.memory.*;
import com.aiep.identity.api.IdentityFacade;
import com.aiep.identity.facade.DatabaseIdentityFacade;
import com.aiep.identity.repository.IdentitySessionMapper;
import com.aiep.platformai.api.dto.*;
import com.baomidou.mybatisplus.extension.spring.MybatisSqlSessionFactoryBean;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.sql.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.*;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** root审SQL后仅自有随机schema；一个实际vertical，不连接模型或Agent、不伪造确认basis。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemorySummaryIntegrationTest {
    static final ObjectMapper JSON=new ObjectMapper();
    record Group(String run,List<String> messages,MemoryContextPacket.Dependency direct) {}
    @Test void freezesRealSourcesCommitsEncryptedCasAndForgetsWithoutResurrection()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message","ai_operation_run"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");
            for(String table:List.of("id_hr_session","id_hr_grant"))sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql",table);
            seed(c);
            String raw;try(var q=c.createStatement();var r=q.executeQuery("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id='policy-operations' AND version_id='v1'")){assertTrue(r.next());raw=r.getString(1);}
            var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
            policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"sourceTypes",List.of("CURRENT_USER_MESSAGE","USER_PREFERENCE_DECISION","MESSAGE","SUMMARY"),
                "executionGrants",List.of(Map.of("node_id","direct","execution_agent_id","operations","purpose","assistant_response")),
                "summary",Map.of("enabled",true,"purposes",List.of("SUMMARY"),"retentionSeconds",900))));
            try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1','policy-operations','summary/1',?,?)")){q.setString(1,policy.toString());q.setBytes(2,random(32));assertEquals(1,q.executeUpdate());}
            try(var q=c.createStatement()){assertEquals(1,q.executeUpdate("UPDATE ai_memory_policy SET current_version_id='summary/1' WHERE tenant_id='t1' AND id='policy-operations'"));}
        }
        var factory=new MybatisSqlSessionFactoryBean();factory.setDataSource(ds);
        factory.setMapperLocations(new ClassPathResource("mapper/memory/MemoryMapper.xml"),new ClassPathResource("mapper/memory/MemoryPacketMapper.xml"),new ClassPathResource("mapper/memory/MemoryRefreshMapper.xml"),new ClassPathResource("mapper/memory/MemorySummaryMapper.xml"),new ClassPathResource("mapper/memory/MemoryForgetMapper.xml"),new ClassPathResource("mapper/identity/IdentitySessionMapper.xml"));
        var conf=new com.baomidou.mybatisplus.core.MybatisConfiguration();conf.setMapUnderscoreToCamelCase(true);factory.setConfiguration(conf);
        var sql=new SqlSessionTemplate(factory.getObject());var memory=sql.getMapper(MemoryMapper.class);var packets=sql.getMapper(MemoryPacketMapper.class);var refresh=sql.getMapper(MemoryRefreshMapper.class);var mapper=sql.getMapper(MemorySummaryMapper.class);
        IdentityFacade identity=new DatabaseIdentityFacade(sql.getMapper(IdentitySessionMapper.class));var actor=identity.authenticate(TOKENS.get("t1:u1")).orElseThrow();
        var scope=new MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",SESSIONS.get("t1:u1:operations:1"));
        var scopes=new MemoryScopePolicy(identity,null);var bindings=new MemorySessionBindingService(memory,scopes,new ConversationScopeResolver());var tx=new DataSourceTransactionManager(ds);
        var codec=new MemoryValueCodec("it","{\"it\":\""+Base64.getEncoder().encodeToString(random(32))+"\"}",Base64.getEncoder().encodeToString(random(32)));
        var policies=new MemoryPolicyService(memory);var dependencies=new MemoryDependencyService(packets);var preferences=new MemoryPreferenceService(memory,scopes,bindings,policies,new MemoryVersionService(memory,codec),codec,tx);
        var pref=preferences.save(actor,new MemoryContracts.PreferenceCommand(scope,"response.language","zh-CN",0,"summary-pref",null));
        var prefDeps=dependencies.dependencies(scope,"MEMORY_VERSION",pref.id(),pref.versionId());assertFalse(prefDeps.isEmpty());
        var issuer=new MemoryPacketService(true,memory,packets,scopes,bindings,policies,preferences,dependencies,codec,tx,Clock.systemUTC(),true,refresh,identity);
        var sources=new MemorySummarySourceService(true,mapper,memory,packets,dependencies,codec,scopes,bindings,identity,tx,Clock.systemUTC());var summaries=new MemorySummaryService(sources);
        var first=group(ds,scope,packets,dependencies,prefDeps);issue(issuer,actor,scope,first.run(),first.direct());
        var frozen=sources.freeze(actor,scope,first.run(),"summary-plan-a",first.messages());assertEquals(2,frozen.frozen().sources().size());assertEquals(1,frozen.frozen().requiredEntries().size());
        assertEquals(first.messages(),frozen.frozen().sources().stream().map(s->s.sourceRef().sourceId()).toList());
        assertTrue(frozen.frozen().sources().stream().allMatch(s->s.sourceRef().sourceType().equals("MESSAGE")&&s.sourceDependencies().contains(s.sourceRef())));
        var other=new MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",SESSIONS.get("t1:u1:operations:2"));
        assertThrows(MemoryContracts.MemoryException.class,()->sources.freeze(actor,other,first.run(),"cross-scope",first.messages()));
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE ai_operation_message SET conversation_id=? WHERE id=?")){q.setString(1,other.sessionId());q.setString(2,first.messages().get(0));assertEquals(1,q.executeUpdate());}
        assertThrows(MemoryContracts.MemoryException.class,()->sources.freeze(actor,scope,first.run(),"summary-plan-a",first.messages()));
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE ai_operation_message SET conversation_id=? WHERE id=?")){q.setString(1,scope.sessionId());q.setString(2,first.messages().get(0));assertEquals(1,q.executeUpdate());}
        var appended=group(ds,scope,packets,dependencies,prefDeps);issue(issuer,actor,scope,appended.run(),appended.direct());
        var later=sources.freeze(actor,scope,appended.run(),"summary-plan-b",appended.messages());
        assertTrue(later.frozen().sources().getFirst().sequence()>frozen.frozen().sources().getLast().sequence());
        var segment=candidate(frozen,"summary-segment-a");assertEquals(segment,summaries.commitSegment(actor,scope,"summary-plan-a",segment));
        assertEquals(segment,summaries.readCommitted(actor,scope,segment.segmentId()));assertEquals(1,summaries.listCommitted(actor,scope).size());
        var exported=summaries.exportCommitted(actor,scope);assertEquals(1,exported.size());
        assertEquals("SUMMARY",exported.getFirst().summaryDependency().sourceType());assertEquals(segment.segmentId(),exported.getFirst().summaryDependency().sourceId());
        assertEquals(MemorySummaryService.segmentDigest(segment),exported.getFirst().summaryDependency().sourceVersion());
        assertTrue(exported.getFirst().currentDependencies().contains(exported.getFirst().summaryDependency()));assertTrue(exported.getFirst().currentDependencies().containsAll(segment.sourceDependencies()));
        var history=List.of(new MemoryHistoryMessage(first.messages().get(0),hash("synthetic original narrative"),"user","synthetic original narrative",dependencies.dependencies(scope,"MESSAGE",first.messages().get(0),hash("synthetic original narrative"))),
            new MemoryHistoryMessage(first.messages().get(1),"1","assistant","synthetic response",dependencies.dependencies(scope,"MESSAGE",first.messages().get(1),"1")));
        var projection=summaries.contextProjection(actor,scope,history);assertNotNull(projection);
        assertEquals("memory-summary-context/1",JSON.readTree(projection.json()).path("contract_version").asText());
        assertEquals(segment.segmentId(),JSON.readTree(projection.json()).at("/summaries/0/segment/segment_id").asText());
        assertFalse(projection.referenceJson().contains("synthetic summary"));assertFalse(projection.referenceJson().contains("synthetic original narrative"));
        assertEquals(projection.json(),summaries.rebuildProjection(actor,scope,projection.referenceJson()).json());
        assertNull(summaries.contextProjection(actor,scope,List.of(history.getFirst())));
        long plansBefore=count(ds,"ai_memory_summary_plan"),segmentsBefore=count(ds,"ai_memory_summary_segment");
        summaries.listCommitted(actor,scope);summaries.readCommitted(actor,scope,segment.segmentId());
        assertEquals(plansBefore,count(ds,"ai_memory_summary_plan"));assertEquals(segmentsBefore,count(ds,"ai_memory_summary_segment"));
        assertEquals(segment,summaries.commitSegment(actor,scope,"summary-plan-a",segment));
        try(var c=ds.getConnection();var q=c.prepareStatement("SELECT encrypted_payload FROM ai_memory_summary_segment WHERE tenant_id='t1' AND id=?")){q.setBytes(1,b(segment.segmentId()));try(var r=q.executeQuery()){assertTrue(r.next());assertNotNull(r.getBytes(1));assertFalse(new String(r.getBytes(1),java.nio.charset.StandardCharsets.UTF_8).contains("synthetic summary"));}}
        // 两个独立原execution冻结相同新消息范围，通过真实两连接争用同scope CAS。
        var third=group(ds,scope,packets,dependencies,prefDeps);issue(issuer,actor,scope,third.run(),third.direct());
        var left=sources.freeze(actor,scope,third.run(),"summary-race-left",third.messages());
        String secondExecution=UUID.randomUUID().toString();issue(issuer,actor,scope,secondExecution,third.direct());
        var right=sources.freeze(actor,scope,secondExecution,"summary-race-right",third.messages());
        var pool=Executors.newFixedThreadPool(2);var start=new CountDownLatch(1);
        try {
            var a=pool.submit(()->{start.await();try{summaries.commitSegment(actor,scope,left.planId(),candidate(left,"race-a"));return true;}catch(MemoryContracts.MemoryException conflict){assertEquals("MEMORY_REVISION_CONFLICT",conflict.code());return false;}});
            var b=pool.submit(()->{start.await();try{summaries.commitSegment(actor,scope,right.planId(),candidate(right,"race-b"));return true;}catch(MemoryContracts.MemoryException conflict){assertEquals("MEMORY_REVISION_CONFLICT",conflict.code());return false;}});
            start.countDown();assertNotEquals(a.get(10,TimeUnit.SECONDS),b.get(10,TimeUnit.SECONDS));
        }finally{pool.shutdownNow();}
        assertEquals(projection.json(),summaries.rebuildProjection(actor,scope,projection.referenceJson()).json());
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE ai_operation_message SET content='changed source' WHERE id=?")){q.setString(1,appended.messages().get(0));assertEquals(1,q.executeUpdate());}
        assertEquals("SUMMARY_STALE",assertThrows(MemoryContracts.MemoryException.class,()->summaries.commitSegment(actor,scope,later.planId(),candidate(later,"stale-b"))).code());
        var forget=new MemoryForgetService(memory,sql.getMapper(MemoryForgetMapper.class),scopes,bindings,codec,tx);
        forget.forget(actor,new MemoryForgetService.ForgetCommand(scope,pref.id(),pref.revision(),"m2-source-forget","FORGET_AND_SUPPRESS"));
        assertThrows(MemoryContracts.MemoryException.class,()->summaries.readCommitted(actor,scope,segment.segmentId()));
        try(var c=ds.getConnection();var q=c.createStatement();var r=q.executeQuery("SELECT COUNT(*) FROM ai_memory_summary_segment WHERE encrypted_payload IS NOT NULL")){assertTrue(r.next());assertEquals(0,r.getInt(1));}
        summaries.forget(actor,scope);assertTrue(summaries.listCommitted(actor,scope).isEmpty());assertThrows(MemoryContracts.MemoryException.class,()->summaries.readCommitted(actor,scope,segment.segmentId()));
        try(var c=ds.getConnection();var q=c.createStatement();var r=q.executeQuery("SELECT (SELECT COUNT(*) FROM ai_memory_summary_segment WHERE state<>'SCRUBBED' OR encrypted_payload IS NOT NULL OR nonce IS NOT NULL OR auth_tag IS NOT NULL OR content_hmac IS NOT NULL),(SELECT COUNT(*) FROM ai_memory_summary_plan WHERE state<>'SCRUBBED' OR encrypted_payload IS NOT NULL OR nonce IS NOT NULL OR auth_tag IS NOT NULL OR content_hmac IS NOT NULL)")){assertTrue(r.next());assertEquals(0,r.getInt(1));assertEquals(0,r.getInt(2));}
        assertThrows(MemoryContracts.MemoryException.class,()->sources.freeze(actor,scope,first.run(),"resurrection",first.messages()));
        System.out.println("M2P1 sourceFreeze=real MESSAGE=originalId preferenceBasis=real sourceMove=denied appendOutside=allowed encryptedCas=passed concurrentCas=one staleCorrection=denied sourceEpochForget=scrubbed localForget=scrubbed readCreatesNothing=true paidCalls=0 mainFlowEnabled=false");
    }
    static void issue(MemoryPacketService issuer,IdentityFacade.Subject actor,MemoryScopeDTO scope,String execution,MemoryContextPacket.Dependency dep)throws Exception {
        issuer.issue(actor,scope,execution,execution,JSON.readTree("{\"message\":\"synthetic request\"}"),Instant.now().getEpochSecond()+300,List.of(dep));
    }
    static Group group(DataSource ds,MemoryScopeDTO scope,MemoryPacketMapper packets,MemoryDependencyService dependencies,List<MemoryContextPacket.Dependency> preference)throws Exception {
        String run=UUID.randomUUID().toString(),user=UUID.randomUUID().toString(),assistant=UUID.randomUUID().toString();String body="synthetic original narrative";
        try(var c=ds.getConnection()) {
            try(var q=c.prepareStatement("INSERT INTO ai_operation_run(id,conversation_id,tenant_id,user_message_id,agent_run_id,status,created_at,updated_at) VALUES(?,?,'t1',?,?,'succeeded',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))")){q.setString(1,run);q.setString(2,scope.sessionId());q.setString(3,user);q.setString(4,"agent-"+run);assertEquals(1,q.executeUpdate());}
            try(var q=c.prepareStatement("INSERT INTO ai_operation_message(id,conversation_id,tenant_id,role,content,run_id,created_at) VALUES(?,?,'t1','user',?,?,UTC_TIMESTAMP(6)),(?,?,'t1','assistant','synthetic response',?,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 1 SECOND))")){q.setString(1,user);q.setString(2,scope.sessionId());q.setString(3,body);q.setString(4,run);q.setString(5,assistant);q.setString(6,scope.sessionId());q.setString(7,run);assertEquals(2,q.executeUpdate());}
        }
        String hash=hash(body),source=UUID.randomUUID().toString();assertEquals(1,packets.insertInputSource(b("t1"),b(source),b(user),b(hash),Instant.now().plusSeconds(1200)));var state=packets.findSource(b("t1"),b(source));
        var direct=new MemoryContextPacket.Dependency(state.sourceType(),source,hash,state.grantEpoch(),state.sourceEpoch(),state.deletionEpoch());
        dependencies.record(scope,"MESSAGE",user,hash,run,List.of(direct),List.of(List.of(direct)),List.of());
        var all=new ArrayList<>(preference);all.add(direct);dependencies.record(scope,"MESSAGE",assistant,"1",run,all,List.of(all),List.of());
        return new Group(run,List.of(user,assistant),direct);
    }
    static SummarySegment candidate(FrozenPlan plan,String id) {
        var frozen=plan.frozen();var refs=frozen.sources().stream().map(SummaryInputSource::sourceRef).toList();
        var goal=new SummaryEntry("narrative","synthetic summary",ContentOrigin.UNCONFIRMED_INFERENCE,DecisionStatus.UNRESOLVED,refs,null,List.of());
        var deps=MemoryPacketDigest.dependencies(frozen.sources().stream().flatMap(s->s.sourceDependencies().stream()).toList());
        return new SummarySegment(id,frozen.scope(),refs,new SummaryWatermark(frozen.sourceRevision(),frozen.sources().getFirst().sequence(),frozen.sources().getLast().sequence()),goal,frozen.requiredEntries(),List.of(),List.of(),List.of(),List.of(),List.of(),deps,frozen.expiresAt());
    }
    static byte[] b(String value){return MemoryMapper.identity(value);}
    static long count(DataSource ds,String table)throws Exception {
        if(!Set.of("ai_memory_summary_plan","ai_memory_summary_segment").contains(table))throw new IllegalArgumentException();
        try(var c=ds.getConnection();var q=c.createStatement();var r=q.executeQuery("SELECT COUNT(*) FROM "+table)){assertTrue(r.next());return r.getLong(1);}
    }
}
