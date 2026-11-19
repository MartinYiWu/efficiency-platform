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
import org.springframework.transaction.support.TransactionTemplate;
import static com.aiep.aihub.memory.MemoryPreferenceIntegrationTest.*;
import static org.junit.jupiter.api.Assertions.*;

/** root已授权随机schema上的真实Mapper/身份/事务；回执为合成Agent边界，不冒充双库或Graph恢复。 */
@EnabledIfSystemProperty(named="memory.integration.enabled",matches="true")
class MemoryRefreshIntegrationTest {
    static final ObjectMapper JSON=new ObjectMapper();
    static byte[] b(String s){return MemoryMapper.identity(s);}
    @Test void originalLoginSamePayloadAndExpiredCandidateAreDurable()throws Exception {
        String url=required("MEMORY_IT_MYSQL_JDBC_URL");var uri=URI.create(url.substring(5));
        assertEquals("127.0.0.1",uri.getHost());assertTrue(uri.getPath().matches("/aiep_memory_it_[0-9]{8}_[0-9a-f]{10}"));
        var ds=new DriverManagerDataSource(url,required("MEMORY_IT_MYSQL_USER"),required("MEMORY_IT_MYSQL_PASSWORD"));
        try(var c=ds.getConnection()) {
            for(String table:List.of("ai_operation_conversation","ai_operation_message"))sourceTable(c,"V1.0.0__operation_assistant_mvp.sql",table);
            sourceTable(c,"V1.1.0__customer_service_knowledge_aihub.sql","ai_customer_service_conversation");
            for(String table:List.of("id_hr_session","id_hr_grant"))sourceTable(c,"V1.2.3__hr_execution_identity_and_sources.sql",table);
            seed(c);
            String raw;
            try(var q=c.createStatement();var r=q.executeQuery("SELECT policy_json FROM ai_memory_policy_version WHERE tenant_id='t1' AND policy_id='policy-operations' AND version_id='v1'")){assertTrue(r.next());raw=r.getString(1);}
            var policy=(com.fasterxml.jackson.databind.node.ObjectNode)JSON.readTree(raw);
            policy.set("context",JSON.valueToTree(Map.of("enabled",true,"packetTtlSeconds",60,"executionTimeoutSeconds",300,"sourceRetentionSeconds",900,
                "sourceTypes",List.of("USER_PREFERENCE_DECISION","CURRENT_USER_MESSAGE"),"executionGrants",List.of(Map.of("node_id","direct","execution_agent_id","operations","purpose","assistant_response")))));
            try(var q=c.prepareStatement("INSERT INTO ai_memory_policy_version(tenant_id,policy_id,version_id,policy_json,content_hmac) VALUES('t1','policy-operations','refresh-it',?,?)")){q.setString(1,policy.toString());q.setBytes(2,random(32));assertEquals(1,q.executeUpdate());}
            try(var q=c.createStatement()){assertEquals(1,q.executeUpdate("UPDATE ai_memory_policy SET current_version_id='refresh-it' WHERE tenant_id='t1' AND id='policy-operations'"));}
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
        var clock=new Clock(){public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId z){return this;}public Instant instant(){return Instant.ofEpochSecond(seconds.get());}};
        var dependencies=new MemoryDependencyService(packets,clock);
        var service=new MemoryPacketService(true,memory,packets,scopes,bindings,policies,preferences,dependencies,codec,tx,clock,true,refresh,identity);
        var scope=new MemoryScopeDTO("t1","u1","operations","operations","CONVERSATION",SESSIONS.get("t1:u1:operations:1"));
        var preference=preferences.save(actor,new MemoryContracts.PreferenceCommand(scope,"response.language","zh-CN",0,"rf05-pref",null));
        String message=UUID.randomUUID().toString(),hash=hash("synthetic-refresh-input");
        try(var c=ds.getConnection();var q=c.prepareStatement("INSERT INTO ai_operation_message(id,conversation_id,tenant_id,role,content,created_at) VALUES(?,?,'t1','user','synthetic-refresh-input',UTC_TIMESTAMP(6))")){q.setString(1,message);q.setString(2,scope.sessionId());assertEquals(1,q.executeUpdate());}
        assertEquals(1,packets.insertInputSource(b("t1"),b("rf05-source"),b(message),b(hash),clock.instant().plusSeconds(900)));
        var source=packets.findSource(b("t1"),b("rf05-source"));assertNotNull(source);
        var direct=new MemoryContextPacket.Dependency(source.sourceType(),"rf05-source",hash,source.grantEpoch(),source.sourceEpoch(),source.deletionEpoch());
        var original=service.issue(actor,scope,"rf05-exec","rf05-exec",JSON.readTree("{\"message\":\"synthetic-refresh-input\"}"),seconds.get()+300,List.of(direct));
        var anchor=refresh.findAnchor(b("t1"),b("rf05-exec"));assertNotNull(anchor);assertArrayEquals(b(actor.sessionRef()),anchor.originalSessionRef());
        seconds.addAndGet(61);var wait=wait(original,1,"rf05-wait","a".repeat(64),0);
        var request=service.prepareRefresh(scope,wait,"rf05-resume");assertEquals(2,request.refreshedContext().packet().packetRevision());
        assertEquals(original.authorization().semanticSnapshotDigest(),request.refreshedContext().authorization().semanticSnapshotDigest());
        assertTrue(request.refreshedContext().packet().expiresAt()<=anchor.sourceRetentionDeadline());
        seconds.addAndGet(61);assertEquals(request,service.prepareRefresh(scope,wait,"rf05-resume"));
        var changed=new MemoryContextWait(wait.contractVersion(),wait.waitEventId(),wait.runtimeId(),wait.taskId(),wait.executionId(),wait.scope(),1,1,wait.expectedCurrentContextFingerprint(),"e".repeat(64),wait.logicalOperationId(),wait.semanticInputHash(),null,1,null,null,wait.checkpointMode(),null,null,wait.waitPhase(),wait.originalDeadline(),0);
        assertEquals("MEMORY_RESUME_CONFLICT",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,changed,"rf05-resume")).code());
        var expired=new MemoryResumeReceipt(MemoryResumeReceipt.Code.MEMORY_REFRESH_PACKET_EXPIRED,"receipt-1",wait.waitEventId(),2L,1L,1L,wait.expectedCurrentContextFingerprint(),1L,MemoryResumeReceipt.State.WAITING_CONTEXT,MemoryResumeReceipt.CandidatePhase.EXPIRED_UNAPPLIED,null,false);
        service.recordReceipt("t1","rf05-exec",request,expired);assertEquals("EXPIRED_UNAPPLIED",refresh.findCandidate(b("t1"),b("rf05-exec"),b("rf05-resume")).phase());
        assertEquals(expired,service.recordReceipt("t1","rf05-exec",request,expired));
        var request2=service.prepareRefresh(scope,wait,"rf05-resume-2");assertEquals(3,request2.refreshedContext().packet().packetRevision());
        var applied=new MemoryResumeReceipt(MemoryResumeReceipt.Code.MEMORY_REFRESH_PACKET_EXPIRED,"receipt-2",wait.waitEventId(),3L,1L,3L,"b".repeat(64),2L,MemoryResumeReceipt.State.WAITING_CONTEXT,MemoryResumeReceipt.CandidatePhase.APPLIED_EXPIRED,"rf05-next-wait",false);
        service.recordReceipt("t1","rf05-exec",request2,applied);assertEquals(3,service.currentAuthorization("t1","rf05-exec").packetRevision());assertFalse(service.currentAuthorization("t1","rf05-exec").dispatchAllowed());
        assertEquals("MEMORY_REVISION_CONFLICT",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,wait,"rf05-old-wait")).code());
        var next=wait(original,3,"rf05-next-wait","b".repeat(64),2);
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE ai_operation_message SET content='changed-input' WHERE id=?")){q.setString(1,message);assertEquals(1,q.executeUpdate());}
        assertEquals("MEMORY_SOURCE_CHANGED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,next,"rf05-source-change")).code());
        try(var c=ds.getConnection();var q=c.prepareStatement("UPDATE ai_operation_message SET content='synthetic-refresh-input' WHERE id=?")){q.setString(1,message);assertEquals(1,q.executeUpdate());}
        preferences.correct(actor,preference.id(),new MemoryContracts.PreferenceCommand(scope,"response.language","en-US",preference.revision(),"rf05-correct",null));
        assertEquals("MEMORY_SOURCE_CHANGED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,next,"rf05-value-change")).code());
        String secondToken=Base64.getUrlEncoder().withoutPadding().encodeToString(random(48));
        try(var c=ds.getConnection()) {
            try(var q=c.prepareStatement("INSERT INTO id_hr_session(credential_hash,tenant_id,user_id,expires_at) VALUES(?,'t1','u1',?)")){q.setString(1,hash(secondToken));q.setTimestamp(2,java.sql.Timestamp.from(Instant.now().plusSeconds(300)));assertEquals(1,q.executeUpdate());}
            try(var q=c.prepareStatement("UPDATE id_hr_session SET revoked_at=UTC_TIMESTAMP(6) WHERE credential_hash=?")){q.setString(1,actor.sessionRef());assertEquals(1,q.executeUpdate());}
        }
        assertTrue(identity.authenticate(secondToken).isPresent());
        assertEquals("ACCESS_REVOKED",assertThrows(MemoryContracts.MemoryException.class,()->service.prepareRefresh(scope,next,"rf05-new-login")).code());
        System.out.println("D16RF05 realMySQL=passed originalLogin=exact candidateReplay=fixed expiry=terminal sourceMutation=denied valueVersionChange=denied newLoginSubstitution=denied paidCalls=0");
    }
    static MemoryContextWait wait(MemoryContextEnvelope original,long revision,String id,String fp,long count) {
        return new MemoryContextWait("memory-context-wait/1",id,"rf05-runtime",original.packet().taskId(),original.packet().executionId(),original.scope(),revision,1,fp,"c".repeat(64),"rf05-op",original.packet().semanticInputHash(),null,1,null,null,MemoryContextWait.CheckpointMode.NONE,null,null,MemoryContextWait.WaitPhase.BEFORE_PREPARE,original.authorization().deadlineEpochSeconds(),count);
    }
}
